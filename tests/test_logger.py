# -*- coding: utf-8 -*-
"""Unit tests for the SQLite activity logger and dig captures."""
import os
import tempfile
import unittest

import cv2
import numpy as np

from core.logger import ActivityLogger, save_capture


class TestActivityLogger(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.logger = ActivityLogger(os.path.join(self._tmp.name, 'activity.db'))

    def tearDown(self):
        self.logger.close()
        self._tmp.cleanup()

    def test_help_event_recorded(self):
        self.logger.log_help()
        records = self.logger.fetch_all()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['event'], 'help')
        self.assertIn('time', records[0])
        self.assertIsNone(records[0]['capture'])

    def test_dig_event_includes_capture_id(self):
        self.logger.log_dig('dig_20260908_120000_000000.jpg')
        records = self.logger.fetch_all()
        self.assertEqual(records[0]['event'], 'dig')
        self.assertEqual(records[0]['capture'], 'dig_20260908_120000_000000.jpg')

    def test_events_append_in_order(self):
        self.logger.log_help()
        self.logger.log_dig('a.jpg')
        self.logger.log_help()
        self.assertEqual([r['event'] for r in self.logger.fetch_all()], ['help', 'dig', 'help'])

    def test_records_persist_across_instances(self):
        self.logger.log_help()
        self.logger.close()
        second = ActivityLogger(self.logger.db_path)
        try:
            self.assertEqual([r['event'] for r in second.fetch_all()], ['help'])
        finally:
            second.close()

    def test_fetch_all_limit_returns_most_recent(self):
        self.logger.log_help()
        self.logger.log_dig('a.jpg')
        self.logger.log_help()
        self.assertEqual([r['event'] for r in self.logger.fetch_all(limit=2)], ['dig', 'help'])

    def test_fetch_all_empty_db(self):
        self.assertEqual(self.logger.fetch_all(), [])

    def test_fetch_by_id(self):
        self.logger.log_help()
        self.logger.log_dig('a.jpg')
        records = self.logger.fetch_all()

        second = self.logger.fetch_by_id(records[1]['id'])
        self.assertEqual(second['event'], 'dig')
        self.assertEqual(second['capture'], 'a.jpg')
        self.assertIsNone(self.logger.fetch_by_id(999))

    def test_lucky_gift_event_recorded(self):
        self.logger.log_lucky_gift('lucky_gift_20260908_120000_000000.jpg')
        records = self.logger.fetch_all()
        self.assertEqual(records[0]['event'], 'lucky_gift')
        self.assertEqual(records[0]['capture'], 'lucky_gift_20260908_120000_000000.jpg')

    def test_launch_event_recorded(self):
        self.logger.log_launch()
        records = self.logger.fetch_all()
        self.assertEqual(records[0]['event'], 'launch')
        self.assertIsNone(records[0]['capture'])


class TestCapture(unittest.TestCase):
    def test_save_capture_returns_id_and_writes_jpg(self):
        img = np.random.RandomState(1).randint(0, 256, (900, 1600, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as tmp:
            file_name = save_capture(img, capture_dir=tmp)
            self.assertIsNotNone(file_name)
            self.assertTrue(file_name.startswith('dig_'), file_name)
            self.assertTrue(file_name.endswith('.jpg'), file_name)

            saved = cv2.imread(os.path.join(tmp, file_name))
            self.assertIsNotNone(saved)
            self.assertEqual(saved.shape, img.shape)

    def test_save_capture_with_custom_prefix(self):
        img = np.random.RandomState(1).randint(0, 256, (90, 160, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as tmp:
            file_name = save_capture(img, prefix='lucky_gift', capture_dir=tmp)
            self.assertIsNotNone(file_name)
            self.assertTrue(file_name.startswith('lucky_gift_'), file_name)

    def test_save_capture_none_image(self):
        self.assertIsNone(save_capture(None))

    def test_capture_filename_has_no_literal_percent_f(self):
        img = np.random.RandomState(1).randint(0, 256, (90, 160, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as tmp:
            file_name = save_capture(img, capture_dir=tmp)
            self.assertIsNotNone(file_name)
            self.assertNotIn('%f', file_name)
            self.assertRegex(file_name, r'^dig_\d{8}_\d{6}_\d{6}\.jpg$')


if __name__ == '__main__':
    unittest.main()
