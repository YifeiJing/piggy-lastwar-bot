# -*- coding: utf-8 -*-
"""OCR wrapper: a lazy, shared rapidocr engine for on-screen text checks.

rapidocr 3.x API: RapidOCR() (bundled PP-OCRv6 models, CPU onnxruntime),
callable with an image, returns RapidOCROutput with .txts/.boxes/.scores."""
import threading
from typing import List

import cv2
from rapidocr import RapidOCR


class OCREngine:
    """Shared, lazily-loaded rapidocr engine.

    The model load takes a few seconds, so the engine is created on first
    use and shared by every task and the engine loop."""

    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._ocr = None
        self._load_lock = threading.Lock()

    @classmethod
    def shared(cls) -> 'OCREngine':
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _engine(self) -> RapidOCR:
        if self._ocr is None:
            with self._load_lock:
                if self._ocr is None:
                    self._ocr = RapidOCR()
        return self._ocr

    def extract_texts(self, image) -> List[str]:
        """All recognized text fragments in the image (empty if none/None)."""
        if image is None:
            return []
        result = self._engine()(image)
        return list(result.txts or [])

    def check_text_exists(self, image, target_text: str) -> bool:
        """True if target_text appears (as a substring) on the screen."""
        return any(target_text in text for text in self.extract_texts(image))

    def recognize_text(self, image_path: str) -> str:
        """OCR a file on disk; returns the joined text."""
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not read the image at {image_path}")
        return ' '.join(self.extract_texts(image))
