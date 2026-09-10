# -*- coding: utf-8 -*-
"""Tests for cooperative task cancellation (kill_event / TaskKilled)."""
import unittest

import numpy as np

from core.cancel import TaskKilled, kill_event
from tasks.base_task import BaseTask


class DummyDriver:
    def screenshot(self):
        return np.zeros((10, 10, 3), np.uint8)


class TestTaskCancellation(unittest.TestCase):
    def setUp(self):
        kill_event.clear()

    def tearDown(self):
        kill_event.clear()

    def test_check_exists_raises_when_killed(self):
        task = BaseTask(DummyDriver())
        kill_event.set()
        with self.assertRaises(TaskKilled):
            task.check_exists('whatever.png')

    def test_wait_and_click_raises_when_killed(self):
        task = BaseTask(DummyDriver())
        kill_event.set()
        with self.assertRaises(TaskKilled):
            task.wait_and_click('whatever.png', timeout=2)

    def test_helpers_work_normally_when_not_killed(self):
        task = BaseTask(DummyDriver())
        # Noise screen + missing template: no match, but no exception either
        self.assertIsNone(task.check_exists('whatever.png'))
        self.assertFalse(task.wait_and_click('whatever.png', timeout=0.2))


if __name__ == '__main__':
    unittest.main()
