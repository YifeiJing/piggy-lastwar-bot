# -*- coding: utf-8 -*-
import os
import queue
import threading
import time

from config import ASSETS_DIR
from core.adb_driver import AdbDriver
from core.cancel import TaskKilled, kill_event
from core.logger import ActivityLogger
from tasks.daily_tasks import (
    AllianceHelpTask,
    DigTask,
    ExitStuckStateTask,
    GameLaunchTask,
    LuckyGiftTask,
    SendChatFlowerTask
)
from vision.matcher import TemplateMatcher
from vision.ocr import OCREngine

TASK_MAP = {
    'help': AllianceHelpTask,
    'dig': DigTask,
    'lucky_gift': LuckyGiftTask,
    'launch': GameLaunchTask,
    'flower': SendChatFlowerTask
}


class Stats:
    def __init__(self):
        self.alliance_help_count = 0
        self.dig_count = 0
        self.lucky_gift_count = 0

    def format_stats(self) -> str:
        return (
            f"Alliance Help Executed: {self.alliance_help_count}\n"
            f"Digging Executed: {self.dig_count}\n"
            f"Lucky Gift Collected: {self.lucky_gift_count}"
        )

    def print_stats(self):
        print("==========================================")
        print("                Stats Report               ")
        print("==========================================")
        print(self.format_stats())


class BotEngine:
    """Controllable game loop: pause/stop events + a queue for remotely
    requested tasks. The loop thread never exits; /stop only halts the
    automatic cycle so manual /run commands still work."""

    def __init__(self, driver: AdbDriver, cycle_interval: float = 3.0, logger: ActivityLogger = None):
        self.driver = driver
        self.stats = Stats()
        self.cycle_interval = cycle_interval
        self.logger = logger or ActivityLogger()
        self.command_queue = queue.Queue()
        self.stop_event = threading.Event()   # set = auto loop stopped
        self.pause_event = threading.Event()  # set = paused
        self.exit_event = threading.Event()   # set = process shutdown
        self.ocr_engine = OCREngine.shared()
        self.current_task = None
        self._notifier = None
        self._thread = None

    # ---- remote control API ----

    def set_notifier(self, fn):
        """fn(text) is called on engine events (logout, task results...)."""
        self._notifier = fn

    @property
    def status(self) -> str:
        if self.pause_event.is_set():
            return 'PAUSED'
        if self.stop_event.is_set():
            return 'STOPPED'
        return 'RUNNING'

    def start(self):
        """Spawn the engine loop thread."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name='bot-engine', daemon=True)
        self._thread.start()

    def wait(self):
        """Block until the engine thread ends (Ctrl+C to exit)."""
        try:
            while self._thread and self._thread.is_alive():
                self._thread.join(timeout=1)
        except KeyboardInterrupt:
            self.exit_event.set()
            if self._thread:
                self._thread.join(timeout=5)

    def start_loop(self):
        if not self.stop_event.is_set() and not self.pause_event.is_set():
            self._notify('ℹ️ Auto loop is already running.')
            return
        self.stop_event.clear()
        self.pause_event.clear()
        self._notify('▶️ Auto loop started.')

    def stop_loop(self):
        if self.stop_event.is_set():
            self._notify('ℹ️ Auto loop is already stopped.')
            return
        self.stop_event.set()
        self._notify('⏹️ Auto loop stopped. Send /start to resume.')

    def pause(self):
        if self.pause_event.is_set() or self.stop_event.is_set():
            self._notify('ℹ️ Auto loop is not running.')
            return
        self.pause_event.set()
        self._notify('⏸️ Paused. Send /resume to continue.')

    def resume(self):
        if not self.pause_event.is_set():
            self._notify('ℹ️ Auto loop is not paused.')
            return
        self.pause_event.clear()
        self._notify('▶️ Resumed.')

    def run_task(self, name: str):
        if name not in TASK_MAP:
            self._notify(f"❓ Unknown task '{name}'. Available: {', '.join(TASK_MAP)}")
            return
        self.command_queue.put(('run', name))
        self._notify(f"🕒 Task '{name}' queued — it will run when the current task finishes.")

    def kill_task(self):
        """Abort the currently running task (dead-loop rescue).

        Sets the kill event; the task raises TaskKilled at its next
        check_exists/wait_and_click call and the engine keeps running."""
        if self.current_task is None:
            self._notify('ℹ️ No task is currently running.')
            return
        kill_event.set()
        self._notify('🗡️ Kill signal sent — the task will abort at its next screen check.')

    # ---- internals ----

    def _notify(self, text: str):
        print(f"[TG] {text}")
        if self._notifier:
            try:
                self._notifier(text)
            except Exception as e:
                print(f"[-] Notifier error: {e}")

    def _loop(self):
        print("[*] Bot engine loop started.")
        while not self.exit_event.is_set():
            # While stopped or paused, only service queued commands.
            while (self.stop_event.is_set() or self.pause_event.is_set()) and not self.exit_event.is_set():
                self._drain_commands()
                time.sleep(0.5)
            self._drain_commands()
            self._game_cycle()
            if not (self.stop_event.is_set() or self.pause_event.is_set()):
                self._sleep(self.cycle_interval)
        print("[*] Bot engine loop exited.")

    def _sleep(self, seconds: float):
        end = time.time() + seconds
        while time.time() < end and not self.exit_event.is_set():
            if self.stop_event.is_set() or self.pause_event.is_set():
                return
            time.sleep(min(0.5, end - time.time()))

    def _drain_commands(self):
        while True:
            try:
                action, name = self.command_queue.get_nowait()
            except queue.Empty:
                return
            if action == 'run':
                self._run_task_once(name)

    def _run_task_once(self, name: str):
        kill_event.clear()
        task = TASK_MAP[name](self.driver)
        self.current_task = name
        self._notify(f"▶️ Starting task: {name}")
        try:
            result = task.run()
            if result:
                self._record_task(name, task)
            self._notify(f"✅ Task '{name}' {'succeeded.' if result else 'failed.'}")
        except TaskKilled:
            self._notify(f"🗡️ Task '{name}' killed.")
        except Exception as e:
            self._notify(f"❌ Task '{name}' error: {e}")
        finally:
            self.current_task = None

    def _record_task(self, name: str, task):
        """Append a completion record to the activity log."""
        if name == 'help':
            self.logger.log_help()
        elif name == 'dig':
            self.logger.log_dig(getattr(task, 'last_capture_id', None))
        elif name == 'lucky_gift':
            self.logger.log_lucky_gift(getattr(task, 'last_capture_id', None))
        elif name == 'launch':
            # Only record when the game was actually started, not every
            # cycle's "already running" check.
            if getattr(task, 'just_launched', False):
                self.logger.log_launch()

    def _game_cycle(self):
        kill_event.clear()
        self.current_task = 'auto cycle'
        try:
            self._cycle_tasks()
        except TaskKilled:
            self._notify('🗡️ Running task killed.')
        finally:
            self.current_task = None

    def _cycle_tasks(self):
        launch_task = GameLaunchTask(self.driver)
        if launch_task.run() and launch_task.just_launched:
            self._record_task('launch', launch_task)
            self._sleep(20)
            if self.stop_event.is_set() or self.pause_event.is_set():
                return

        help_task = AllianceHelpTask(self.driver)
        if help_task.run():
            self.stats.alliance_help_count += 1
            self._record_task('help', help_task)
        dig_task = DigTask(self.driver)
        dig_task.set_notifier(self._notify)
        if dig_task.run():
            self.stats.dig_count += 1
            self._record_task('dig', dig_task)
        lucky_gift_task = LuckyGiftTask(self.driver)
        lucky_gift_task.set_notifier(self._notify)
        if lucky_gift_task.run():
            self.stats.lucky_gift_count += 1
            self._record_task('lucky_gift', lucky_gift_task)
        if self._detect_logout():
            self.stats.print_stats()
            self.driver.tap(450, 900)
            self.stop_event.set()
            self._notify('⚠️ Logout detected — auto loop stopped. Send /start to resume.')
            return

        exit_stuck_task = ExitStuckStateTask(self.driver)
        if not exit_stuck_task.run():
        
            self.stats.print_stats()
            self.stop_event.set()
            self._notify('⚠️ Stuck state detected and recovery failed — auto loop stopped. Send /start to resume.')

    def _detect_logout(self) -> bool:
        img = self.driver.screenshot()
        if img is None:
            return False
        matcher = TemplateMatcher()
        pos = matcher.find_template(img, os.path.join(ASSETS_DIR, 'logout_notification.png'))
        if pos:
            print('Detected logout state...')
            return True
        return False

    def _detect_stuck(self) -> bool:
        img = self.driver.screenshot()
        if img is None:
            return False
        matcher = TemplateMatcher()
        pos_base = matcher.find_template(img, os.path.join(ASSETS_DIR, 'base_btn.png'))
        pos_world = matcher.find_template(img, os.path.join(ASSETS_DIR, 'world_btn.png'))
        if not pos_base and not pos_world:
            return True
        return False
