# -*- coding: utf-8 -*-
"""MuMu Player IPC driver.

Drives the bot through MuMu's external_renderer_ipc.dll instead of adb, exposing
the same surface AdbDriver does (screenshot/tap/swipe/press_back) so tasks, the
engine and the Telegram controller stay driver-agnostic.

Verified against MuMu Player nx (core_version 6.8.2.0, 900x1600 portrait):
  * nemu_connect() takes the emulator ROOT (the parent of nx_main), not nx_main
    itself; MuMuManager.exe and the DLL do live inside nx_main.
  * nemu_get_display_id() must be called with an empty package name — the
    Chinese display alias MuMu安卓设备 is rejected with -1. Display id 0 is valid,
    so "not bound yet" is tracked as -1.
  * the frame is RGBA and bottom-up; reversed to BGR and flipped upright it
    matches `adb exec-out screencap -p` at 0.04 mean abs diff.
  * the DLL exports no touch-move primitive, so drags step with repeated
    touch_down calls (the only mechanism this API offers).
  * nemu_input_event_key_down/up deliver nothing on the nx line (verified
    against keycodes 1/3/4/8/13/27/111), so BACK runs through MuMuManager's
    player shell instead.

Public methods preserved for compatibility:
  - connect(), get_display_id(), capture_display(), screenshot()
  - key_down(), key_up(), touch_down(), touch_up()
  - finger_touch_down(), finger_touch_up()
  - tap(), send_keyevent(), back(), press_back()
  - swipe(), swipe_ext()
"""
import ctypes
import json
import os
import random
import re
import subprocess
import threading
import time
from typing import Any, Callable, Optional, Sequence, Tuple

import numpy as np

# Fallbacks used when config.py has no MuMu settings (standalone tools, __main__).
SIMULATOR_FOLDER = r'E:\mumu\MuMuPlayer\nx_main'
SIMULATOR_INDEX = 0


def _config_get(key: str, default: Any) -> Any:
    """Read a setting from config.py, falling back when it is absent."""
    try:
        import config
    except ImportError:
        return default
    return getattr(config, key, default)


class MuMuIpcError(RuntimeError):
    pass


class Logger:

    def debug(self, msg: str):
        print(f"[DEBUG] {msg}")

    def info(self, msg: str):
        print(f"[INFO] {msg}")

    def error(self, msg: str):
        print(f"[ERROR] {msg}")

logger = Logger()


class Device:
    def exit(self):
        logger.info("Device exit called.")


class MuMu12IPC:
    """
    Drop-in replacement implementing display capture and input injection via MuMu
    12 external_renderer_ipc.dll.
    """

    def __init__(self, device: Device = None, simulator_index: Optional[int] = None,
                 folder: Optional[str] = None):
        self.device = device
        # Normalize emulator folder from config (compatible with your project layout)
        norm = os.path.normpath(folder or _config_get('MUMU_SIMULATOR_FOLDER', SIMULATOR_FOLDER))
        # nemu_connect() wants the emulator root; the DLL and MuMuManager.exe sit
        # one level down, in nx_main.
        self._emu_root = (
            os.path.dirname(norm)
            if os.path.basename(norm).lower() in ["shell", "nx_main"]
            else norm
        )
        self._folder = norm
        self._manager = os.path.join(self._folder, "MuMuManager.exe")

        # MuMuManager.exe and nemu_connect() both use a 0-based instance index.
        if simulator_index is None:
            simulator_index = _config_get('SIMULATOR_INDEX', SIMULATOR_INDEX)
        self._index: int = int(simulator_index)
        self._app_index: int = 0  # 0 works for single-game bind; adjust if multi instance mapping needed

        self._conn: int = 0
        self._display_id: int = -1  # -1 = not bound yet (display id 0 is valid)
        self._lock = threading.RLock()  # engine thread and Telegram commands share one IPC handle

        # Capture size hint; the API reports the real size back and we adopt it.
        self._hint_w: int = int(_config_get('SCREEN_WIDTH', 900))
        self._hint_h: int = int(_config_get('SCREEN_HEIGHT', 1600))
        self._buf_w: int = 0
        self._buf_h: int = 0
        self._buffer = None  # single reusable framebuffer

        self._setting_info = None
        self._dll = None
        self._is_new_coord: Optional[bool] = None  # coord system flag (>= 4.1.21)

        self.device_id = f"mumu:{self._index}"  # AdbDriver parity for logs/tools

        # Preload to fail-fast with clear diagnostics
        self._load_renderer()

    # -----------------------
    # Loading / version logic
    # -----------------------
    def _load_renderer(self):
        """
        Load external_renderer_ipc.dll from typical MuMu 12 locations.
        """
        candidates = [
            os.path.join(self._folder, "sdk", "external_renderer_ipc.dll"),
            os.path.join(self._emu_root, "shell", "sdk", "external_renderer_ipc.dll"),
            os.path.join(self._emu_root, "nx_main", "sdk", "external_renderer_ipc.dll"),
            os.path.join(self._emu_root, "sdk", "external_renderer_ipc.dll"),
        ]
        last_err = None
        for path in candidates:
            try:
                self._dll = ctypes.CDLL(path)
                logger.debug(f"Loaded MuMu renderer DLL: {path}")
                break
            except OSError as e:
                last_err = e
                logger.debug(f"Failed to load renderer from {path}: {e}")
        if self._dll is None:
            msg = f"Cannot load external_renderer_ipc.dll. Checked: {candidates}. Last error: {last_err}"
            logger.error(msg)
            raise MuMuIpcError(msg)

        # Bind types only after successful load
        self._dll.nemu_connect.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        self._dll.nemu_connect.restype = ctypes.c_int

        self._dll.nemu_disconnect.argtypes = [ctypes.c_int]
        self._dll.nemu_disconnect.restype = None

        self._dll.nemu_get_display_id.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._dll.nemu_get_display_id.restype = ctypes.c_int

        self._dll.nemu_capture_display.argtypes = [
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ubyte),
        ]
        self._dll.nemu_capture_display.restype = ctypes.c_int

        self._dll.nemu_input_event_touch_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_touch_down.restype = ctypes.c_int

        self._dll.nemu_input_event_touch_up.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dll.nemu_input_event_touch_up.restype = ctypes.c_int

        self._dll.nemu_input_event_finger_touch_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_finger_touch_down.restype = ctypes.c_int

        self._dll.nemu_input_event_finger_touch_up.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_finger_touch_up.restype = ctypes.c_int

        self._dll.nemu_input_event_key_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_key_down.restype = ctypes.c_int

        self._dll.nemu_input_event_key_up.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_key_up.restype = ctypes.c_int

    def _manager_json(self, subcmd: str) -> dict:
        """
        Call MuMuManager.exe to get JSON for 'setting' or 'info' and decode.
        """
        cmd = [self._manager, subcmd, "-v", str(self._index), "-a"]
        try:
            out = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            ).stdout.strip()
            return json.loads(out)
        except Exception as e:
            raise Exception(f"MuMuManager `{subcmd}` failed: {e}")

    def get_setting_core_version(self) -> str:
        """获取模拟器 core_version 信息，只执行一次并缓存"""
        if self._setting_info is None:
            cmd = [
                self._manager,
                "setting",
                "-v",
                str(self._index),
                "get_key",
                "core_version",
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                self._setting_info = result.stdout.strip()
                logger.debug(f"MuMu core_version: {self._setting_info}")
            except Exception as e:
                logger.error(f"获取 MuMu setting 失败: {e}")
                raise
        return self._setting_info

    def _emu_version(self) -> tuple:
        """
        Returns (major, minor, patch) for decision-making. Caches coord mapping rule.
        """
        version = self.get_setting_core_version()
        try:
            parts = tuple(int(x) for x in version.split(".")[:3])
        except ValueError:
            logger.error(f"无法解析 MuMu core_version: {version!r}")
            parts = (0, 0, 0)
        if self._is_new_coord is None:
            # MuMu 12 changed coordinate arguments to logical x/y in 4.1.21; the
            # nx line (6.x) reports portrait frames and takes them as-is.
            self._is_new_coord = parts >= (4, 1, 21)
            logger.info(
                f"MuMu {version}: using {'logical' if self._is_new_coord else 'legacy'} coordinates."
            )
        return parts

    def get_emulator_info(self) -> Optional[str]:
        """获取模拟器运行状态（实时查询），无法解析时返回 None"""
        cmd = [self._manager, "api", "-v", str(self._index), "player_state"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except Exception as e:
            logger.error(f"获取 MuMu 模拟器 info 失败: {e}")
            return None
        stdout = result.stdout
        match1 = re.search(r"player index: (\d+)(?:\r\n|\r|\n)", stdout)
        if not match1 or int(match1.group(1)) != self._index:
            logger.error(f"MuMu player index 不匹配: {stdout.strip()!r}")
            return None
        match2 = re.search(r"state: state=([^\s\r\n]+)(?:\r\n|\r|\n|$)", stdout)
        if not match2:
            logger.error(f"无法解析 MuMu state: {stdout.strip()!r}")
            return None
        return match2.group(1)

    def _emu_state(self) -> str:
        """
        'running' | 'launching' | 'stopped'
        """
        data = self.get_emulator_info()
        if data == "start_finished":
            return "running"
        if data in ("starting_vm", "starting_rom"):
            return "launching"
        return "stopped"

    # -----------------------
    # Connection & display
    # -----------------------
    def connect(self):
        """
        Establish IPC connection to emulator if running.
        """
        if self._emu_state() != "running":
            raise MuMuIpcError("模拟器未启动，请启动模拟器")
        self._conn = self._dll.nemu_connect(ctypes.c_wchar_p(self._emu_root), self._index)
        if self._conn == 0:
            raise MuMuIpcError("连接模拟器失败，请启动模拟器")
        logger.info(f"MuMu IPC connected (root={self._emu_root!r}, index={self._index}).")

    def get_display_id(self) -> int:
        """
        Bind to the emulator display. Display id 0 is valid, so failures are
        reported as negative values and -1 means "not bound yet".
        """
        last = -1
        for pkg in (b"", "MuMu安卓设备".encode("utf-8")):
            display_id = self._dll.nemu_get_display_id(self._conn, pkg, self._app_index)
            if display_id >= 0:
                self._display_id = display_id
                logger.debug(f"Display bound: id={display_id} (pkg={pkg!r})")
                return display_id
            last = display_id
        raise MuMuIpcError(f"获取Display ID失败 (last={last})")

    def _ensure_ready(self):
        """
        Ensure connection and display id are valid; auto-recover if needed.
        """
        if self._conn == 0:
            self.connect()
        if self._display_id < 0:
            self.get_display_id()

    def _reset_connection(self):
        """Drop the IPC handle so the next call reconnects.

        A single dropped frame or rejected input must not take the bot down, so
        this recovers in place instead of signalling process exit."""
        if self._conn:
            try:
                self._dll.nemu_disconnect(self._conn)
            except Exception:
                pass
        self._conn = 0
        self._display_id = -1
        self._buf_w = self._buf_h = 0
        self._buffer = None

    # -----------------------
    # Capture
    # -----------------------
    def _grab(self, w: int, h: int) -> Tuple[int, int, int, Any]:
        """One raw framebuffer read. Returns (ret, w, h, buffer)."""
        size = max(1, w) * max(1, h) * 4
        if self._buffer is None or len(self._buffer) != size:
            self._buffer = (ctypes.c_ubyte * size)()
        buffer = self._buffer
        out_w = ctypes.c_int(w)
        out_h = ctypes.c_int(h)
        ret = self._dll.nemu_capture_display(
            self._conn,
            self._display_id,
            size,
            ctypes.byref(out_w),
            ctypes.byref(out_h),
            buffer,
        )

        return ret, out_w.value, out_h.value, buffer

    def capture_display(self) -> Optional[np.ndarray]:
        """
        Capture one frame as HxWx3 BGR numpy array, upside-up, or None on failure.

        The buffer is reused across calls; it is only reallocated when the
        emulator reports a size different from the cached one.
        """
        with self._lock:
            try:
                self._ensure_ready()

                ret, w, h, buffer = self._grab(self._buf_w or self._hint_w, self._buf_h or self._hint_h)
                if ret != 0:
                    # Size hint was wrong — retry once with whatever the API reported.
                    ret, w, h, buffer = self._grab(w or self._hint_w, h or self._hint_h)
                if ret != 0:
                    raise MuMuIpcError(f"capture failed: ret={ret}")
                if (w, h) != (self._buf_w, self._buf_h):
                    logger.debug(f"Capture size adopted: {w}x{h}")
                    self._buf_w, self._buf_h = w, h

                # RGBA -> BGR (matches adb screencap), then flip upright. Copy so
                # the caller keeps a stable frame: the buffer is reused by the
                # next capture, and tasks hold a screen across later driver calls.
                frame = np.frombuffer(buffer, dtype=np.uint8).reshape((h, w, 4))[:, :, :3]
                return np.ascontiguousarray(np.flipud(frame[:, :, ::-1]))
                # return np.flipud(frame[:, :, ::-1])
            except Exception as e:
                logger.error(f"capture_display error: {e}")
                self._reset_connection()
                return None

    def screenshot(self) -> Optional[np.ndarray]:
        """AdbDriver-compatible capture: BGR frame, or None when it fails."""
        return self.capture_display()

    def _map_xy(self, x: int, y: int) -> Tuple[int, int]:
        """
        Map logical coordinates to MuMu IPC expected arguments depending on version.
        """
        if self._is_new_coord is None:
            self._emu_version()
        if self._is_new_coord:
            return int(x), int(y)
        return int((self._buf_h or self._hint_h) - y), int(x)

    # -----------------------
    # Input
    # -----------------------
    def _input_error(self, op: str, e: Exception):
        logger.error(f"{op} error: {e}")
        self._reset_connection()

    def key_down(self, key_code: int):
        with self._lock:
            try:
                self._ensure_ready()
                rc = self._dll.nemu_input_event_key_down(
                    self._conn, self._display_id, int(key_code)
                )
                if rc != 0:
                    raise MuMuIpcError(f"key_down failed: {rc}")
            except Exception as e:
                self._input_error('key_down', e)

    def key_up(self, key_code: int):
        with self._lock:
            try:
                self._ensure_ready()
                rc = self._dll.nemu_input_event_key_up(
                    self._conn, self._display_id, int(key_code)
                )
                if rc != 0:
                    raise MuMuIpcError(f"key_up failed: {rc}")
            except Exception as e:
                self._input_error('key_up', e)

    def touch_down(self, x: int, y: int):
        with self._lock:
            try:
                self._ensure_ready()
                tx, ty = self._map_xy(x, y)
                rc = self._dll.nemu_input_event_touch_down(
                    self._conn, self._display_id, tx, ty
                )
                if rc != 0:
                    raise MuMuIpcError(f"touch_down failed: {rc}")
            except Exception as e:
                self._input_error('touch_down', e)

    def touch_up(self):
        with self._lock:
            try:
                self._ensure_ready()
                rc = self._dll.nemu_input_event_touch_up(self._conn, self._display_id)
                if rc != 0:
                    raise MuMuIpcError(f"touch_up failed: {rc}")
            except Exception as e:
                self._input_error('touch_up', e)

    def finger_touch_down(self, finger_id: int, x: int, y: int):
        with self._lock:
            try:
                self._ensure_ready()
                tx, ty = self._map_xy(x, y)
                rc = self._dll.nemu_input_event_finger_touch_down(
                    self._conn, self._display_id, int(finger_id), tx, ty
                )
                if rc != 0:
                    raise MuMuIpcError(f"finger_touch_down failed: {rc}")
            except Exception as e:
                self._input_error('finger_touch_down', e)

    def finger_touch_up(self, finger_id: int):
        with self._lock:
            try:
                self._ensure_ready()
                rc = self._dll.nemu_input_event_finger_touch_up(
                    self._conn, self._display_id, int(finger_id)
                )
                if rc != 0:
                    raise MuMuIpcError(f"finger_touch_up failed: {rc}")
            except Exception as e:
                self._input_error('finger_touch_up', e)

    def tap(self, x: int, y: int, jitter: int = 4, sleep_time: float = 0.4,
            hold_time: float = 0.05):
        """AdbDriver-compatible tap: jittered position, hold, then settle."""
        actual_x = int(x + random.randint(-jitter, jitter))
        actual_y = int(y + random.randint(-jitter, jitter))
        with self._lock:
            self.touch_down(actual_x, actual_y)
            time.sleep(hold_time)
            self.touch_up()
        if sleep_time:
            time.sleep(sleep_time + random.uniform(0.05, 0.15))

    def send_keyevent(self, key_code: int, hold_time: float = 0.1):
        with self._lock:
            self.key_down(key_code)
            time.sleep(hold_time)
            self.key_up(key_code)

    def _player_shell(self, cmd: str) -> bool:
        """Run a command in the player's Android shell via MuMuManager.

        MuMu documents this as the equivalent of `adb shell <cmd>`, and it needs
        no adb connection of our own.
        """
        try:
            result = subprocess.run(
                [self._manager, "sh", "-v", str(self._index), "--cmd", cmd],
                capture_output=True, text=True, timeout=15,
            )
        except Exception as e:
            logger.error(f"MuMuManager sh {cmd!r} failed: {e}")
            return False
        if result.returncode != 0 or "errcode" in result.stdout:
            logger.error(f"MuMuManager sh {cmd!r} failed: {result.stdout.strip()}{result.stderr.strip()}")
            return False
        return True

    def back(self) -> bool:
        """Press Android BACK.

        The renderer's key-event entry points accept key_down/key_up but deliver
        nothing on the nx line — keycodes 1/3/4/8/13/27/111 were all verified to
        leave the screen untouched — so BACK goes through the player shell
        (`go_back` == `adb shell input keyevent 4`) and only falls back to the
        IPC key event if that fails.
        """
        if self._player_shell("go_back"):
            return True
        logger.error("go_back 失败，尝试 IPC keyevent 4")
        self.send_keyevent(4)
        return False

    def press_back(self) -> bool:
        """AdbDriver-compatible back press (+ settle)."""
        ok = self.back()
        time.sleep(0.5)
        return ok

    def _swipe_path(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        duration: float = 0.5,
        steps: int = 30,
        fall: bool = True,
        lift: bool = True,
        interval: float = 0.0,
    ):
        """Step a drag between two points.

        The DLL exposes no touch-move entry point, so each step re-issues
        touch_down at the interpolated position — that is the only drag
        mechanism the IPC API offers."""
        if fall:
            self.touch_down(x0, y0)

        # 每步耗时
        dt = duration / steps

        for i in range(1, steps + 1):
            tx = int(x0 + (x1 - x0) * (i / steps))
            ty = int(y0 + (y1 - y0) * (i / steps))
            self.touch_down(tx, ty)
            time.sleep(dt)

        if lift:
            if interval:
                time.sleep(interval)
            self.touch_up()

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 350,
              steps: int = 30):
        """AdbDriver-compatible swipe: duration in milliseconds, then settle."""
        with self._lock:
            self._swipe_path(
                x1, y1, x2, y2,
                duration=max(0.01, duration_ms / 1000.0),
                steps=steps,
                interval=0.45
            )
        time.sleep(random.uniform(0.4, 0.6))

    def swipe_ext(
        self,
        points: Sequence[Tuple[int, int]],
        durations: Sequence[int],
        update: bool = False,
        interval: float = 0.0,
        func: Callable[[np.ndarray], Any] = lambda _: None,
    ):
        if len(points) < 2 or len(durations) != len(points) - 1:
            raise ValueError(
                "swipe_ext requires at least 2 points and len(durations)==len(points)-1"
            )

        with self._lock:
            for i, (p0, p1, d_ms) in enumerate(zip(points[:-1], points[1:], durations)):
                self._swipe_path(
                    p0[0],
                    p0[1],
                    p1[0],
                    p1[1],
                    duration=max(0.01, d_ms / 1000.0),
                    fall=(i == 0),
                    lift=(i == len(durations) - 1),
                    interval=interval if i == len(durations) - 1 else 0.0,
                )

        if update:
            func(self.capture_display())


if __name__ == "__main__":
    import cv2

    ipc = MuMu12IPC(device=Device())
    ipc.connect()
    start = time.perf_counter()
    frame = ipc.screenshot()
    elapsed = time.perf_counter() - start
    if frame is None:
        raise SystemExit("capture failed")
    print(f"Captured frame shape: {frame.shape} in {elapsed:.4f}s")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = _config_get('DUMP_DIR', os.path.join(here, 'dumps'))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'mumu_capture.png')
    cv2.imwrite(out_path, frame)
    print(f"Saved {out_path}")
