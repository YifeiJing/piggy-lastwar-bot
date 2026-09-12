# -*- coding: utf-8 -*-
"""Dry-run tests: engine control plane + full game loop, no device, no Telegram.

Run from the project root:
    venv/bin/python -m unittest discover -s tests -v
"""
import os
import tempfile
import threading
import time
import unittest

import numpy as np

import core.engine as engine_mod
from core.cancel import TaskKilled, kill_event
from core.engine import BotEngine
from core.logger import ActivityLogger


class FakeDriver:
    """Mimics AdbDriver without adb: random-noise fake screen, records inputs."""

    def __init__(self):
        self._rng = np.random.RandomState(42)
        self.taps = []
        self.screenshots = 0
        self.backs = 0

    def screenshot(self):
        self.screenshots += 1
        return self._rng.randint(0, 256, (900, 1600, 3), dtype=np.uint8)

    def tap(self, x, y, **kwargs):
        self.taps.append((x, y))

    def swipe(self, *args, **kwargs):
        pass

    def press_back(self):
        self.backs += 1


class QuietEngine(BotEngine):
    """Engine whose game cycle is a no-op — for testing the control plane only."""

    def __init__(self, driver, logger=None):
        super().__init__(driver, cycle_interval=0.2, logger=logger)

    def _game_cycle(self):
        pass


class FakeResultTask:
    """Stand-in for a real task class: returns a fixed result instantly."""

    def __init__(self, driver, result=False):
        self.driver = driver
        self.result = result
        self._notifier = None

    def set_notifier(self, fn):
        self._notifier = fn

    def run(self):
        return self.result


def make_task_class(result):
    return lambda driver: FakeResultTask(driver, result)


def wait_for(predicate, timeout=10.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class EngineTestCase(unittest.TestCase):
    def setUp(self):
        kill_event.clear()
        self.driver = FakeDriver()
        self.messages = []
        self._tmp = tempfile.TemporaryDirectory()
        self.logger = ActivityLogger(os.path.join(self._tmp.name, 'activity.db'))
        self.engine = self.make_engine()
        self.engine.set_notifier(self.messages.append)
        self._orig_tasks = {
            name: getattr(engine_mod, name)
            for name in ('AllianceHelpTask', 'DigTask', 'ExitStuckStateTask', 'LuckyGiftTask', 'GameLaunchTask')
        }

    def make_engine(self):
        return QuietEngine(self.driver, logger=self.logger)

    def tearDown(self):
        self.engine.exit_event.set()
        if self.engine._thread:
            self.engine._thread.join(timeout=5)
        for name, cls in self._orig_tasks.items():
            setattr(engine_mod, name, cls)
        engine_mod.TASK_MAP['help'] = self._orig_tasks['AllianceHelpTask']
        engine_mod.TASK_MAP['dig'] = self._orig_tasks['DigTask']
        engine_mod.TASK_MAP['lucky_gift'] = self._orig_tasks['LuckyGiftTask']
        engine_mod.TASK_MAP['launch'] = self._orig_tasks['GameLaunchTask']
        kill_event.clear()
        self.logger.close()
        self._tmp.cleanup()


class TestStateMachine(EngineTestCase):
    def test_status_and_guard_transitions(self):
        e = self.engine
        e.start()
        self.assertEqual(e.status, 'STOPPED')  # starts stopped

        e.start_loop()
        self.assertEqual(e.status, 'RUNNING')
        e.start_loop()     # guard: already running
        e.pause()
        self.assertEqual(e.status, 'PAUSED')
        e.pause()          # guard: already paused
        e.resume()
        self.assertEqual(e.status, 'RUNNING')
        e.resume()         # guard: not paused
        e.stop_loop()
        self.assertEqual(e.status, 'STOPPED')
        e.stop_loop()      # guard: already stopped
        e.start_loop()
        self.assertEqual(e.status, 'RUNNING')

        self.assertEqual(self.messages, [
            '▶️ Auto loop started.',
            'ℹ️ Auto loop is already running.',
            '⏸️ Paused. Send /resume to continue.',
            'ℹ️ Auto loop is not running.',
            '▶️ Resumed.',
            'ℹ️ Auto loop is not paused.',
            '⏹️ Auto loop stopped. Send /start to resume.',
            'ℹ️ Auto loop is already stopped.',
            '▶️ Auto loop started.',
        ])

    def test_run_task_queued_and_executed(self):
        e = self.engine
        e.start()
        engine_mod.TASK_MAP['help'] = make_task_class(True)

        e.run_task('help')
        self.assertIn("🕒 Task 'help' queued — it will run when the current task finishes.", self.messages)

        # The engine thread drains the queue even while running.
        self.assertTrue(wait_for(
            lambda: any("✅ Task 'help' succeeded." == m for m in self.messages), timeout=5))

        e.run_task('nope')
        self.assertIn("❓ Unknown task 'nope'. Available: help, dig, lucky_gift, launch, flower", self.messages)

    def test_run_task_reports_failure(self):
        e = self.engine
        e.start()
        engine_mod.TASK_MAP['help'] = make_task_class(False)

        e.run_task('help')
        self.assertTrue(wait_for(
            lambda: any("✅ Task 'help' failed." == m for m in self.messages), timeout=5))


class StuckEngine(BotEngine):
    """Real loop flow, but logout detection is controlled."""

    def __init__(self, driver, logout=False, logger=None):
        super().__init__(driver, cycle_interval=0.2, logger=logger)
        self._logout = logout

    def _detect_logout(self):
        return self._logout


class TestLoopRecovery(EngineTestCase):
    def make_engine(self):
        return StuckEngine(self.driver, logger=self.logger)

    def _patch_tasks(self):
        engine_mod.AllianceHelpTask = make_task_class(False)
        engine_mod.DigTask = make_task_class(False)
        engine_mod.ExitStuckStateTask = make_task_class(False)

    def test_stuck_detection_stops_loop_and_notifies(self):
        self._patch_tasks()
        e = self.engine
        e.start()
        e.start_loop()

        self.assertTrue(wait_for(e.stop_event.is_set, timeout=10))
        self.assertIn('⚠️ Stuck state detected and recovery failed — auto loop stopped. Send /start to resume.', self.messages)
        self.assertEqual(e.status, 'STOPPED')
        self.assertEqual(e.stats.alliance_help_count, 0)
        # The loop thread stays alive so manual /run and /start keep working.
        self.assertTrue(e._thread.is_alive())

    def test_logout_detection_stops_loop_and_notifies(self):
        e = StuckEngine(self.driver, logout=True, logger=self.logger)
        e.set_notifier(self.messages.append)
        self.engine = e
        self._patch_tasks()
        e.start()
        e.start_loop()

        self.assertTrue(wait_for(e.stop_event.is_set, timeout=10))
        self.assertIn('⚠️ Logout detected — auto loop stopped. Send /start to resume.', self.messages)
        self.assertEqual(self.driver.taps, [(450, 900)])
        self.assertEqual(e.status, 'STOPPED')


class TestKillTask(EngineTestCase):
    def test_kill_rescues_dead_loop_task(self):
        class DeadLoopTask:
            def __init__(self, driver):
                pass

            def run(self):
                while True:
                    if kill_event.is_set():
                        raise TaskKilled('killed by user')
                    time.sleep(0.01)

        engine_mod.TASK_MAP['help'] = DeadLoopTask
        e = self.engine
        e.start()

        e.run_task('help')
        self.assertTrue(wait_for(
            lambda: any('▶️ Starting task: help' == m for m in self.messages), timeout=5))

        e.kill_task()
        self.assertTrue(wait_for(
            lambda: any("🗡️ Task 'help' killed." == m for m in self.messages), timeout=5))

        # The engine thread survives the kill; loop remains in stopped state
        # (engine started stopped — only /start changes that).
        self.assertTrue(e._thread.is_alive())
        self.assertIsNone(e.current_task)
        self.assertEqual(e.status, 'STOPPED')

    def test_kill_with_no_running_task_reports_idle(self):
        e = self.engine
        e.start()
        e.kill_task()
        self.assertIn('ℹ️ No task is currently running.', self.messages)
        self.assertFalse(kill_event.is_set())


class TestFullDryRun(EngineTestCase):
    """End-to-end: real engine, real tasks, real template matcher, fake screen."""

    def make_engine(self):
        return BotEngine(self.driver, cycle_interval=0.5, logger=self.logger)

    def test_real_cycle_on_fake_screen_terminates_cleanly(self):
        e = self.engine
        e.start()
        e.start_loop()

        # On a noise screen no template ever matches: the cycle should detect
        # the "stuck" state, fail to recover, stop the loop — and never crash.
        self.assertTrue(wait_for(e.stop_event.is_set, timeout=30))
        self.assertGreater(self.driver.screenshots, 0)
        self.assertIn('⚠️ Stuck state detected and recovery failed — auto loop stopped. Send /start to resume.', self.messages)
        self.assertTrue(e._thread.is_alive())

        # A /start resumes the cycle after the stop.
        e.start_loop()
        self.assertEqual(e.status, 'RUNNING')


class TestActivityRecording(EngineTestCase):
    def _read_records(self):
        return self.logger.fetch_all()

    def test_queued_help_and_dig_are_recorded_with_capture(self):
        class FakeDigTask:
            last_capture_id = 'dig_20260908_120000_000000.jpg'

            def __init__(self, driver):
                pass

            def run(self):
                return True

        engine_mod.TASK_MAP['help'] = make_task_class(True)
        engine_mod.TASK_MAP['dig'] = FakeDigTask
        e = self.engine
        e.start()

        e.run_task('help')
        e.run_task('dig')
        self.assertTrue(wait_for(
            lambda: any("✅ Task 'dig' succeeded." == m for m in self.messages), timeout=5))

        records = self._read_records()
        self.assertEqual([r['event'] for r in records], ['help', 'dig'])
        self.assertIn('time', records[0])
        self.assertEqual(records[1]['capture'], 'dig_20260908_120000_000000.jpg')

    def test_failed_task_is_not_recorded(self):
        engine_mod.TASK_MAP['help'] = make_task_class(False)
        e = self.engine
        e.start()

        e.run_task('help')
        self.assertTrue(wait_for(
            lambda: any("✅ Task 'help' failed." == m for m in self.messages), timeout=5))

        self.assertEqual(self._read_records(), [])

    def test_lucky_gift_recorded_with_capture(self):
        class FakeLuckyTask:
            last_capture_id = 'lucky_gift_20260908_120000_000000.jpg'

            def __init__(self, driver):
                pass

            def run(self):
                return True

        engine_mod.TASK_MAP['lucky_gift'] = FakeLuckyTask
        e = self.engine
        e.start()

        e.run_task('lucky_gift')
        self.assertTrue(wait_for(
            lambda: any("✅ Task 'lucky_gift' succeeded." == m for m in self.messages), timeout=5))

        records = self._read_records()
        self.assertEqual([r['event'] for r in records], ['lucky_gift'])
        self.assertEqual(records[0]['capture'], 'lucky_gift_20260908_120000_000000.jpg')

    def test_launch_recorded_only_when_game_was_started(self):
        class FakeLaunchTask:
            def __init__(self, driver, just_launched):
                self.just_launched = just_launched

            def run(self):
                return True

        e = self.engine
        e.start()

        # Game already running: task succeeds but nothing is recorded
        engine_mod.TASK_MAP['launch'] = lambda d: FakeLaunchTask(d, False)
        e.run_task('launch')
        self.assertTrue(wait_for(
            lambda: any("✅ Task 'launch' succeeded." == m for m in self.messages), timeout=5))
        self.assertEqual(self._read_records(), [])

        # Game actually launched: a 'launch' record is appended
        engine_mod.TASK_MAP['launch'] = lambda d: FakeLaunchTask(d, True)
        e.run_task('launch')
        self.assertTrue(wait_for(
            lambda: len(self._read_records()) == 1, timeout=5))
        records = self._read_records()
        self.assertEqual(records[0]['event'], 'launch')
        self.assertIsNone(records[0]['capture'])

    def test_photo_notifier_fired_on_successful_capture_tasks(self):
        class FakeCaptureTask:
            last_capture_id = 'fake.jpg'

            def __init__(self, driver):
                pass

            def run(self):
                return True

        engine_mod.TASK_MAP['dig'] = FakeCaptureTask
        engine_mod.TASK_MAP['lucky_gift'] = FakeCaptureTask
        photos = []
        self.engine.set_photo_notifier(lambda name, capture: photos.append((name, capture)))
        e = self.engine
        e.start()

        e.run_task('dig')
        e.run_task('lucky_gift')
        self.assertTrue(wait_for(lambda: len(photos) == 2, timeout=5))
        self.assertEqual(photos, [('dig', 'fake.jpg'), ('lucky_gift', 'fake.jpg')])

    def test_photo_notifier_not_fired_on_failure(self):
        class FakeFailTask:
            last_capture_id = 'fake.jpg'

            def __init__(self, driver):
                pass

            def run(self):
                return False

        engine_mod.TASK_MAP['dig'] = FakeFailTask
        photos = []
        self.engine.set_photo_notifier(lambda name, capture: photos.append((name, capture)))
        e = self.engine
        e.start()

        e.run_task('dig')
        self.assertTrue(wait_for(
            lambda: any("✅ Task 'dig' failed." == m for m in self.messages), timeout=5))
        time.sleep(0.3)
        self.assertEqual(photos, [])


if __name__ == '__main__':
    unittest.main()
