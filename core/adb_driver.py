# -*- coding: utf-8 -*-
import os
import time
import random
import subprocess
import threading
from typing import Optional
import cv2
import numpy as np


class AdbDriver:
    def __init__(self, device_id: str):
        self.device_id = device_id
        self._lock = threading.RLock()
        self._ensure_connection()

    def _ensure_connection(self):
        with self._lock:
            res = subprocess.run(['adb', 'connect', self.device_id], capture_output=True, text=True)
            print(f"[*] ADB status: {res.stdout.strip()}")

    def shell(self, cmd: str) -> str:
        with self._lock:
            command = ['adb', '-s', self.device_id, 'shell'] + cmd.split()
            res = subprocess.run(command, capture_output=True, text=True)
            return res.stdout

    def screenshot(self) -> Optional[np.ndarray]:
        with self._lock:
            try:
                pipe = subprocess.Popen(
                    ['adb', '-s', self.device_id, 'exec-out', 'screencap', '-p'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                raw_data, _ = pipe.communicate()
                if not raw_data:
                    return None
                return cv2.imdecode(np.frombuffer(raw_data, dtype=np.uint8), cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"[-] Screenshot error: {e}")
                return None

    def tap(self, x: int, y: int, jitter: int = 4, sleep_time: float = 0.4):
        actual_x = int(x + random.randint(-jitter, jitter))
        actual_y = int(y + random.randint(-jitter, jitter))
        self.shell(f"input tap {actual_x} {actual_y}")
        time.sleep(sleep_time + random.uniform(0.05, 0.15))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 350):
        self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")
        time.sleep(random.uniform(0.4, 0.6))

    def press_back(self):
        self.shell("input keyevent 4")
        time.sleep(0.5)
