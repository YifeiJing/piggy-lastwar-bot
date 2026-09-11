# -*- coding: utf-8 -*-
"""Tests for the Telegram controller's history/record commands (no network)."""
import asyncio
import os
import tempfile
import unittest

import numpy as np
from telegram.error import BadRequest

import telegram_controller as tg_mod
from core.logger import ActivityLogger, save_capture
from telegram_controller import TelegramController


class FakeBot:
    def __init__(self, photo_error=None):
        self.messages = []
        self.photos = []
        self.photo_error = photo_error

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append(text)

    async def send_photo(self, chat_id, photo, caption=None, **kwargs):
        if self.photo_error:
            raise self.photo_error
        self.photos.append((photo, caption))


class StubEngine:
    def __init__(self, logger, ocr_engine=None):
        self.logger = logger
        self.ocr_engine = ocr_engine or FakeOCREngine()


class FakeOCREngine:
    def __init__(self):
        self.texts = ['Gift Available', 'Claim']

    def extract_texts(self, image):
        return self.texts

    def check_text_exists(self, image, target_text):
        return any(target_text in text for text in self.texts)


class FakeDriver:
    _NOISE = np.random.RandomState(1).randint(0, 256, (90, 160, 3), dtype=np.uint8)

    def __init__(self, img=_NOISE):
        self.img = img

    def screenshot(self):
        return self.img


class TestHistoryCommands(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.logger = ActivityLogger(os.path.join(self._tmp.name, 'activity.db'))
        self.ocr = FakeOCREngine()
        self.engine = StubEngine(self.logger, self.ocr)
        # Legacy single-engine form: controller wraps it in a dict internally.
        self.controller = TelegramController(self.engine, None)
        self.bot = FakeBot()
        # Replace the real bot with the fake — no network calls
        self.controller.application.bot = self.bot
        # Isolate the capture dir so tests never touch the real dig_captures/
        self._orig_capture_dir = tg_mod.DIG_CAPTURE_DIR
        tg_mod.DIG_CAPTURE_DIR = self._tmp.name

    def tearDown(self):
        tg_mod.DIG_CAPTURE_DIR = self._orig_capture_dir
        self.logger.close()
        self._tmp.cleanup()

    def _run(self, coro):
        return asyncio.run(coro)

    # ---- /history ----

    def test_empty_db_reports_no_records(self):
        self._run(self.controller._send_history(123, self.engine, 10))
        self.assertEqual(self.bot.messages, ['📋 No records yet.'])
        self.assertEqual(self.bot.photos, [])

    def test_history_is_text_only_with_record_ids(self):
        img = np.random.RandomState(1).randint(0, 256, (90, 160, 3), dtype=np.uint8)
        file_name = save_capture(img, capture_dir=self._tmp.name)
        self.logger.log_help()
        self.logger.log_dig(file_name)
        ids = [r['id'] for r in self.logger.fetch_all()]

        self._run(self.controller._send_history(123, self.engine, 10))

        self.assertEqual(len(self.bot.messages), 1)
        summary = self.bot.messages[0]
        self.assertIn('Last 2 records', summary)
        self.assertIn('help', summary)
        self.assertIn(file_name, summary)
        for record_id in ids:
            self.assertIn(f'{record_id}. [', summary)
        # No images in /history
        self.assertEqual(self.bot.photos, [])

    # ---- /record ----

    def test_record_with_capture_sends_photo(self):
        img = np.random.RandomState(1).randint(0, 256, (90, 160, 3), dtype=np.uint8)
        file_name = save_capture(img, capture_dir=self._tmp.name)
        self.logger.log_dig(file_name)
        record_id = self.logger.fetch_all()[0]['id']

        self._run(self.controller._send_record(123, self.engine, record_id))

        self.assertEqual(len(self.bot.messages), 1)
        self.assertTrue(self.bot.messages[0].startswith('#'), self.bot.messages[0])
        self.assertIn(file_name, self.bot.messages[0])
        self.assertEqual(len(self.bot.photos), 1)
        self.assertIn(file_name, self.bot.photos[0][1])

    def test_record_without_capture_sends_info_only(self):
        self.logger.log_help()
        record_id = self.logger.fetch_all()[0]['id']

        self._run(self.controller._send_record(123, self.engine, record_id))

        self.assertEqual(len(self.bot.messages), 1)
        self.assertIn('help', self.bot.messages[0])
        self.assertEqual(self.bot.photos, [])

    def test_record_unknown_id(self):
        self._run(self.controller._send_record(123, self.engine, 999))
        self.assertEqual(self.bot.messages, ['❌ No record with id 999.'])
        self.assertEqual(self.bot.photos, [])

    def test_record_missing_capture_file(self):
        self.logger.log_dig('dig_missing.jpg')
        record_id = self.logger.fetch_all()[0]['id']

        self._run(self.controller._send_record(123, self.engine, record_id))

        self.assertEqual(len(self.bot.messages), 2)
        self.assertTrue(any('is missing' in m for m in self.bot.messages), self.bot.messages)
        self.assertEqual(self.bot.photos, [])

    def test_record_photo_send_error(self):
        img = np.random.RandomState(1).randint(0, 256, (90, 160, 3), dtype=np.uint8)
        file_name = save_capture(img, capture_dir=self._tmp.name)
        self.logger.log_dig(file_name)
        record_id = self.logger.fetch_all()[0]['id']

        self.bot = FakeBot(photo_error=BadRequest('Image_process_failed'))
        self.controller.application.bot = self.bot

        self._run(self.controller._send_record(123, self.engine, record_id))

        self.assertEqual(self.bot.photos, [])
        self.assertTrue(any(f"Couldn't send capture {file_name}" in m for m in self.bot.messages), self.bot.messages)

    # ---- /capture ----

    def test_capture_saves_file_and_replies(self):
        result = self._run(self.controller._save_capture(123, FakeDriver(), 'manual'))
        self.assertTrue(result)
        self.assertTrue(any('💾 Saved' in m and 'manual_' in m for m in self.bot.messages), self.bot.messages)
        files = [f for f in os.listdir(self._tmp.name) if f.endswith('.jpg')]
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith('manual_'), files)

    def test_capture_failure_when_screenshot_none(self):
        result = self._run(self.controller._save_capture(123, FakeDriver(img=None), 'manual'))
        self.assertFalse(result)
        self.assertTrue(any('❌ Screenshot failed' in m for m in self.bot.messages))

    # ---- /ocr ----

    def test_ocr_recognizes_screen_text(self):
        self._run(self.controller._recognize_text(123, self.engine, FakeDriver()))
        self.assertTrue(any('Gift Available' in m for m in self.bot.messages), self.bot.messages)

    def test_ocr_no_text_recognized(self):
        self.ocr.texts = []
        self._run(self.controller._recognize_text(123, self.engine, FakeDriver()))
        self.assertTrue(any('No text recognized' in m for m in self.bot.messages))

    def test_ocr_check_text_found(self):
        self._run(self.controller._check_text(123, self.engine, FakeDriver(), 'Gift'))
        self.assertTrue(any("✅ Found 'Gift' on screen." in m for m in self.bot.messages), self.bot.messages)

    def test_ocr_check_text_not_found(self):
        self._run(self.controller._check_text(123, self.engine, FakeDriver(), 'gold'))
        self.assertTrue(any("❌ 'gold' not found on screen." in m for m in self.bot.messages), self.bot.messages)


if __name__ == '__main__':
    unittest.main()
