# -*- coding: utf-8 -*-
"""Focused tests for LuckyGiftTask's screen sequence (scripted, no device)."""
import os
import unittest

import numpy as np

import tasks.daily_tasks as dt_mod
from tasks.daily_tasks import GameLaunchTask, LuckyGiftTask, SendChatFlowerTask


class FakeDriver:
    def __init__(self, screen=None):
        self.backs = 0
        self.taps = []
        self.screen = screen if screen is not None else np.zeros((90, 160, 3), dtype=np.uint8)

    def screenshot(self):
        return self.screen

    def press_back(self):
        self.backs += 1

    def tap(self, x, y, **kwargs):
        self.taps.append((x, y))


class ScriptedLuckyGiftTask(LuckyGiftTask):
    """wait_and_click follows a script of (template_file, result) entries."""

    def __init__(self, driver, script):
        super().__init__(driver)
        self._script = list(script)

    def wait_and_click(self, template_path, timeout=10, interval=0.8):
        if not self._script:
            return False
        expected, result = self._script.pop(0)
        name = os.path.basename(template_path)
        if name != expected:
            raise AssertionError(f"expected click on {expected}, got {name}")
        return result


class TestLuckyGiftTask(unittest.TestCase):
    def setUp(self):
        self.driver = FakeDriver()
        self.captured_prefixes = []
        self._orig_save_capture = dt_mod.save_capture

        def fake_save_capture(img, prefix='dig', capture_dir=None):
            self.captured_prefixes.append(prefix)
            return 'fake_capture.jpg'

        dt_mod.save_capture = fake_save_capture

    def tearDown(self):
        dt_mod.save_capture = self._orig_save_capture

    def _full_script(self, like_result):
        return [
            ('lucky_gift_notification.png', True),
            ('lucky_gift_share_frame.png', True),
            ('gift_open_btn.png', True),
            ('like_btn.png', like_result),
            ('lucky_gift_list_exit.jpg', True),
            ('go_back_btn.png', True),
        ]

    def test_gift_recorded_even_when_like_button_missing(self):
        task = ScriptedLuckyGiftTask(self.driver, self._full_script(like_result=False))
        self.assertTrue(task.run())
        self.assertEqual(task.last_capture_id, 'fake_capture.jpg')
        self.assertEqual(self.captured_prefixes, ['lucky_gift'])
        self.assertEqual(task._script, [])  # whole exit sequence consumed

    def test_gift_recorded_when_like_succeeds(self):
        task = ScriptedLuckyGiftTask(self.driver, self._full_script(like_result=True))
        self.assertTrue(task.run())
        self.assertEqual(task.last_capture_id, 'fake_capture.jpg')
        self.assertEqual(self.captured_prefixes, ['lucky_gift'])
        self.assertEqual(task._script, [])

    def test_no_notification_means_no_action(self):
        task = ScriptedLuckyGiftTask(self.driver, [('lucky_gift_notification.png', False)])
        self.assertFalse(task.run())
        self.assertIsNone(task.last_capture_id)
        self.assertEqual(self.captured_prefixes, [])
        self.assertEqual(self.driver.backs, 0)

    def test_share_frame_missing_means_no_action(self):
        task = ScriptedLuckyGiftTask(self.driver, [
            ('lucky_gift_notification.png', True),
            ('lucky_gift_share_frame.png', False),
        ])
        self.assertFalse(task.run())
        self.assertIsNone(task.last_capture_id)
        self.assertEqual(self.captured_prefixes, [])


class FakeMatcher:
    def __init__(self, result):
        self.result = result

    def find_template(self, *args, **kwargs):
        return self.result


class TestGameLaunchTask(unittest.TestCase):
    def test_game_already_running(self):
        # 1600x900 screen = game is up: success, nothing tapped
        driver = FakeDriver(screen=np.zeros((1600, 900, 3), dtype=np.uint8))
        task = GameLaunchTask(driver)
        self.assertTrue(task.run())
        self.assertFalse(task.just_launched)
        self.assertEqual(driver.taps, [])

    def test_launches_game_from_home_screen(self):
        driver = FakeDriver(screen=np.zeros((900, 1600, 3), dtype=np.uint8))
        task = GameLaunchTask(driver)
        task.matcher = FakeMatcher((100, 100))
        self.assertTrue(task.run())
        self.assertTrue(task.just_launched)
        self.assertEqual(driver.taps, [(100, 100)])

    def test_game_icon_not_found(self):
        driver = FakeDriver(screen=np.zeros((900, 1600, 3), dtype=np.uint8))
        task = GameLaunchTask(driver)
        task.matcher = FakeMatcher(None)
        self.assertFalse(task.run())
        self.assertFalse(task.just_launched)
        self.assertEqual(driver.taps, [])

    def test_screenshot_failed(self):
        driver = FakeDriver(screen=None)
        task = GameLaunchTask(driver)
        self.assertFalse(task.run())
        self.assertFalse(task.just_launched)


class ScriptedFlowerTask(SendChatFlowerTask):
    """wait_and_click follows a script of (template_file, result) entries."""

    def __init__(self, driver, script):
        super().__init__(driver)
        self._script = list(script)

    def check_exists(self, template_path, threshold=0.82):
        return None  # no alliance-chat button on the fake screen

    def wait_and_click(self, template_path, timeout=10, interval=0.8):
        if not self._script:
            return False
        expected, result = self._script.pop(0)
        name = os.path.basename(template_path)
        if name != expected:
            raise AssertionError(f"expected click on {expected}, got {name}")
        return result


class TestSendChatFlowerTask(unittest.TestCase):
    def setUp(self):
        self.driver = FakeDriver()
        self._orig_go_to_chat = dt_mod.GoToChatTask

    def tearDown(self):
        dt_mod.GoToChatTask = self._orig_go_to_chat

    def _make_task(self, script, chat_opens=True):
        class FakeGoToChat:
            def __init__(self, driver):
                pass

            def run(self):
                return chat_opens

        dt_mod.GoToChatTask = FakeGoToChat
        return ScriptedFlowerTask(self.driver, script)

    def test_flower_sent_successfully(self):
        task = self._make_task([
            ('send_emoji_btn.png', True),
            ('send_flower_emoji.png', True),
            ('send_msg_btn.png', True),
            ('go_back_btn.png', True),
        ])
        self.assertTrue(task.run())

    def test_flower_button_missing_returns_false(self):
        task = self._make_task([
            ('send_emoji_btn.png', True),
            ('send_flower_emoji.png', False),
        ])
        self.assertFalse(task.run())

    def test_chat_failed_to_open_returns_false(self):
        task = self._make_task([], chat_opens=False)
        self.assertFalse(task.run())


if __name__ == '__main__':
    unittest.main()
