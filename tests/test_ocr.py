# -*- coding: utf-8 -*-
"""Unit tests for OCREngine and BaseTask OCR wiring (fake rapidocr — no model)."""
import unittest

import numpy as np

import vision.ocr as ocr_mod
from tasks.base_task import BaseTask
from vision.ocr import OCREngine


class FakeResult:
    def __init__(self, txts):
        self.txts = tuple(txts)


class FakeRapidOCR:
    instances = 0

    def __init__(self):
        FakeRapidOCR.instances += 1

    def __call__(self, image):
        return FakeResult(('Gift Available', 'Claim', 'x50'))


class TestOCREngine(unittest.TestCase):
    def setUp(self):
        self._orig_rapidocr = ocr_mod.RapidOCR
        self._orig_instance = OCREngine._instance
        OCREngine._instance = None
        ocr_mod.RapidOCR = FakeRapidOCR
        FakeRapidOCR.instances = 0

    def tearDown(self):
        ocr_mod.RapidOCR = self._orig_rapidocr
        OCREngine._instance = self._orig_instance

    def _img(self):
        return np.zeros((10, 10, 3), np.uint8)

    def test_shared_returns_same_instance(self):
        self.assertIs(OCREngine.shared(), OCREngine.shared())

    def test_lazy_load_creates_model_once(self):
        engine = OCREngine()
        self.assertEqual(FakeRapidOCR.instances, 0)
        engine.extract_texts(self._img())
        engine.extract_texts(self._img())
        self.assertEqual(FakeRapidOCR.instances, 1)

    def test_extract_texts(self):
        engine = OCREngine()
        self.assertEqual(engine.extract_texts(self._img()), ['Gift Available', 'Claim', 'x50'])
        self.assertEqual(engine.extract_texts(None), [])

    def test_check_text_exists(self):
        engine = OCREngine()
        self.assertTrue(engine.check_text_exists(self._img(), 'Gift'))
        self.assertTrue(engine.check_text_exists(self._img(), 'Claim'))
        self.assertFalse(engine.check_text_exists(self._img(), 'gold'))
        self.assertFalse(engine.check_text_exists(None, 'Gift'))


class FakeSharedOCR:
    def __init__(self):
        self.checked = []

    def check_text_exists(self, image, target_text):
        self.checked.append(target_text)
        return target_text == 'gift'


class TestBaseTaskOCR(unittest.TestCase):
    def setUp(self):
        self._orig_instance = OCREngine._instance
        OCREngine._instance = FakeSharedOCR()

    def tearDown(self):
        OCREngine._instance = self._orig_instance

    def test_check_text_exists_uses_shared_engine(self):
        class DummyDriver:
            def screenshot(self):
                return np.zeros((10, 10, 3), np.uint8)

        task = BaseTask(DummyDriver())
        self.assertTrue(task.check_text_exists('gift'))
        self.assertFalse(task.check_text_exists('flower'))
        self.assertEqual(OCREngine._instance.checked, ['gift', 'flower'])


if __name__ == '__main__':
    unittest.main()
