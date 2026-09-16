# -*- coding: utf-8 -*-
"""Focused tests for LuckyGiftTask's screen sequence (scripted, no device)."""
import os
import unittest

import numpy as np

import tasks.daily_tasks as dt_mod
from core.cancel import TaskKilled, kill_event
from tasks.daily_tasks import AllianceHelpTask, ExitStuckStateTask, GameLaunchTask, LuckyGiftTask, SendChatFlowerTask


class FakeDriver:
    _NOISE = np.zeros((90, 160, 3), dtype=np.uint8)

    def __init__(self, screen=_NOISE):
        self.backs = 0
        self.taps = []
        self.screenshots = 0
        self.screen = screen

    def screenshot(self):
        self.screenshots += 1
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


class FakeMatcherByTemplate:
    """find_template keyed on the template file basename; records searches."""

    def __init__(self, positions):
        self.positions = positions  # basename -> (x, y) or None
        self.searches = []

    def find_template(self, screen, template_path, threshold=0.82, scan_area=None):
        name = os.path.basename(template_path)
        self.searches.append(name)
        return self.positions.get(name)


class TestExitStuckStateTask(unittest.TestCase):
    def setUp(self):
        kill_event.clear()

    def tearDown(self):
        kill_event.clear()

    def _make_task(self, driver, positions):
        task = ExitStuckStateTask(driver)
        task.matcher = FakeMatcherByTemplate(positions)
        return task

    def test_healthy_screen_uses_one_screenshot(self):
        driver = FakeDriver()
        task = self._make_task(driver, {'base_btn.png': (100, 100)})
        self.assertTrue(task.run())
        self.assertEqual(driver.screenshots, 1)
        self.assertEqual(driver.taps, [])
        # base_btn found: world/shop/distance checks are short-circuited
        self.assertNotIn('shop_btn.png', task.matcher.searches)

    def test_healthy_screen_dismisses_distance_hud(self):
        driver = FakeDriver()
        task = self._make_task(driver, {
            'base_btn.png': (100, 100),
            'base_distance_btn.png': (400, 800),
        })
        self.assertTrue(task.run())
        self.assertEqual(driver.screenshots, 1)
        self.assertEqual(driver.taps, [(400, 800)])

    def test_chat_stuck_taps_go_back_from_same_frame(self):
        driver = FakeDriver()
        task = self._make_task(driver, {'go_back_btn.png': (60, 1500)})
        self.assertTrue(task.run())
        self.assertEqual(driver.screenshots, 1)
        self.assertEqual(driver.taps, [(60, 1500)])

    def test_gather_stuck_taps_cancel_from_same_frame(self):
        driver = FakeDriver()
        task = self._make_task(driver, {
            'gather_location_confirm_frame.png': (200, 200),
            'gather_location_cancel_btn.png': (400, 700),
        })
        self.assertTrue(task.run())
        self.assertEqual(driver.screenshots, 1)
        self.assertEqual(driver.taps, [(400, 700)])

    def test_gather_stuck_without_cancel_returns_false(self):
        driver = FakeDriver()
        task = self._make_task(driver, {'gather_location_confirm_frame.png': (200, 200)})
        self.assertFalse(task.run())
        self.assertEqual(driver.screenshots, 1)
        self.assertEqual(driver.taps, [])

    def test_base_stuck_opens_and_exits_shop(self):
        driver = FakeDriver()
        task = self._make_task(driver, {
            'shop_btn.png': (300, 400),
            'shop_exit_btn.png': (800, 800),
        })
        self.assertTrue(task.run())
        # one detection frame + one fresh frame for the shop exit wait
        self.assertEqual(driver.screenshots, 2)
        self.assertEqual(driver.taps, [(300, 400), (800, 800)])

    def test_base_stuck_without_shop_returns_false(self):
        driver = FakeDriver()
        task = self._make_task(driver, {})
        self.assertFalse(task.run())
        self.assertEqual(driver.screenshots, 1)
        self.assertEqual(driver.taps, [])

    def test_screenshot_none_returns_false(self):
        task = ExitStuckStateTask(FakeDriver(screen=None))
        self.assertFalse(task.run())

    def test_kill_event_aborts(self):
        kill_event.set()
        task = ExitStuckStateTask(FakeDriver())
        with self.assertRaises(TaskKilled):
            task.run()


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


class TestPreDetectedInputs(unittest.TestCase):
    """Cycle pre-detection paths: run() reuses the frame/position the engine
    already found instead of taking its own screenshot."""

    def setUp(self):
        kill_event.clear()

    def tearDown(self):
        kill_event.clear()

    def test_help_trigger_taps_without_screenshot(self):
        driver = FakeDriver()
        task = AllianceHelpTask(driver)
        self.assertTrue(task.run(trigger_pos=(111, 222)))
        self.assertEqual(driver.taps, [(111, 222)])
        self.assertEqual(driver.screenshots, 0)

    def test_exit_stuck_reuses_given_frame(self):
        driver = FakeDriver()
        task = ExitStuckStateTask(driver)
        task.matcher = FakeMatcherByTemplate({'base_btn.png': (100, 100)})
        frame = np.zeros((90, 160, 3), dtype=np.uint8)
        self.assertTrue(task.run(screen=frame))
        self.assertEqual(driver.screenshots, 0)
        self.assertEqual(driver.taps, [])

    def test_game_launch_reuses_given_frame(self):
        driver = FakeDriver()
        task = GameLaunchTask(driver)
        self.assertTrue(task.run(screen=np.zeros((1600, 900, 3), dtype=np.uint8)))
        self.assertFalse(task.just_launched)
        self.assertEqual(driver.screenshots, 0)

    def test_lucky_gift_trigger_taps_then_follows_script(self):
        driver = FakeDriver()
        self._orig_save_capture = dt_mod.save_capture
        dt_mod.save_capture = lambda img, prefix='dig', capture_dir=None: 'fake_capture.jpg'
        try:
            task = ScriptedLuckyGiftTask(driver, [
                ('lucky_gift_share_frame.png', True),
                ('gift_open_btn.png', True),
                ('like_btn.png', True),
                ('lucky_gift_list_exit.jpg', True),
                ('go_back_btn.png', True),
            ])
            self.assertTrue(task.run(trigger_pos=(10, 10)))
        finally:
            dt_mod.save_capture = self._orig_save_capture
        self.assertEqual(driver.taps[0], (10, 10))  # notification tap, no screenshot first
        self.assertEqual(task._script, [])  # whole flow consumed
        self.assertEqual(task.last_capture_id, 'fake_capture.jpg')


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
