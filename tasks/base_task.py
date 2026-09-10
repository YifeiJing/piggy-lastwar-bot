# -*- coding: utf-8 -*-
import time
from typing import Optional, Tuple
from core.adb_driver import AdbDriver
from core.cancel import TaskKilled, kill_event
from vision.matcher import TemplateMatcher
from vision.ocr import OCREngine


class BaseTask:
    def __init__(self, driver: AdbDriver):
        self.driver = driver
        self.matcher = TemplateMatcher()
        self.ocr_engine = OCREngine.shared()
        self._notifier = None

    def _notify(self, text: str):
        print(f"[TG] {text}")
        if self._notifier:
            try:
                self._notifier(text)
            except Exception as e:
                print(f"[-] Notifier error: {e}")

    def set_notifier(self, fn):
        """fn(text) is called on engine events (logout, task results...)."""
        self._notifier = fn

    def _raise_if_killed(self):
        if kill_event.is_set():
            raise TaskKilled('task killed by user')

    def wait_and_click(self, template_path: str, timeout: int = 10, interval: float = 0.8) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            self._raise_if_killed()
            screen = self.driver.screenshot()
            if screen is not None:
                pos = self.matcher.find_template(screen, template_path)
                if pos:
                    self.driver.tap(pos[0], pos[1])
                    return True
            time.sleep(interval)
        return False

    def check_exists(self, template_path: str, threshold: float = 0.82) -> Optional[Tuple[int, int]]:
        self._raise_if_killed()
        screen = self.driver.screenshot()
        if screen is None:
            return None
        return self.matcher.find_template(screen, template_path, threshold)

    def check_text_exists(self, target_text: str) -> bool:
        screen = self.driver.screenshot()
        if screen is None:
            return False
        return self.ocr_engine.check_text_exists(screen, target_text)

    def dismiss_popups(self, close_btn_template: str, max_attempts: int = 3):
        for _ in range(max_attempts):
            pos = self.check_exists(close_btn_template, threshold=0.8)
            if pos:
                self.driver.tap(pos[0], pos[1])
                time.sleep(0.6)
            else:
                break

    def run(self):
        raise NotImplementedError("Subclasses must implement run()")
