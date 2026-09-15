# -*- coding: utf-8 -*-
"""OCR wrapper: a lazy, shared rapidocr engine for on-screen text checks.

rapidocr 3.x API: RapidOCR() (bundled PP-OCRv6 models, CPU onnxruntime),
callable with an image, returns RapidOCROutput with .txts/.boxes/.scores."""
import threading
from typing import List

import cv2
from rapidocr import RapidOCR
import time


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

    def extract_texts(self, image, scan_area: Optional[Tuple[int, int, int, int]] = None) -> List[str]:
        """All recognized text fragments in the image (empty if none/None)."""
        if image is None:
            return []
        if scan_area:
            image = image[scan_area[1]:scan_area[3], scan_area[0]:scan_area[2]]
        result = self._engine()(image)
        return list(result.txts or [])

    def check_text_exists(self, image, target_text: str, scan_area: Optional[Tuple[int, int, int, int]] = None) -> bool:
        """True if target_text appears (as a substring) on the screen."""
        return any(target_text in text for text in self.extract_texts(image, scan_area=scan_area))

    def recognize_text(self, image_path: str) -> str:
        """OCR a file on disk; returns the joined text."""
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not read the image at {image_path}")
        return ' '.join(self.extract_texts(image))
        
    def get_text_position(self, image, target_text: str, scan_area: Optional[Tuple[int, int, int, int]] = None):
        """Returns the bounding box of the target_text if found, else None."""
        if image is None:
            return None
        result = self._engine()(image)
        for text, box in zip(result.txts or [], result.boxes or []):
            if target_text in text:
                if scan_area:
                    # Adjust the box coordinates based on the scan area
                    adjusted_box = [
                        box[0] + scan_area[0],
                        box[1] + scan_area[1],
                        box[2] + scan_area[0],
                        box[3] + scan_area[1]
                    ]
                    return adjusted_box
                else:
                    return box  # Return the bounding box of the first match
        return None

def measure_ocr_performance(image, iterations: int = 10) -> float:
    """Measures the average time taken for OCR over a number of iterations."""
    ocr_engine = OCREngine.shared()
    total_time = 0.0
    for _ in range(iterations):
        start_time = time.perf_counter()
        ocr_engine.extract_texts(image)
        end_time = time.perf_counter()
        total_time += (end_time - start_time)
    average_time = total_time / iterations
    return average_time