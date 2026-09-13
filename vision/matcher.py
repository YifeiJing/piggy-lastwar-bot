# -*- coding: utf-8 -*-
from typing import Optional, Tuple, List
import cv2
import numpy as np
import time


class TemplateMatcher:
    @staticmethod
    def find_template(screen: np.ndarray, template_path: str, threshold: float = 0.82) -> Optional[Tuple[int, int]]:
        template = cv2.imread(template_path)
        if template is None or screen is None:
            return None

        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val >= threshold:
            h, w = template.shape[:2]
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return center_x, center_y
        return None

    @staticmethod
    def find_all_templates(screen: np.ndarray, template_path: str, threshold: float = 0.82) -> List[Tuple[int, int]]:
        template = cv2.imread(template_path)
        if template is None or screen is None:
            return []

        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= threshold)
        h, w = template.shape[:2]

        points = []
        for pt in zip(*loc[::-1]):
            points.append((pt[0] + w // 2, pt[1] + h // 2))
        return points

def measure_template_matching_performance(screen: np.ndarray, template_path: str, threshold: float = 0.82, iterations: int = 10, scan_range = None) -> float:
    total_time = 0.0
    screen_to_use = screen if scan_range is None else screen[scan_range[1]:scan_range[3], scan_range[0]:scan_range[2]]
    for _ in range(iterations):
        start_time = time.perf_counter()
        TemplateMatcher.find_template(screen_to_use, template_path, threshold)
        end_time = time.perf_counter()
        total_time += (end_time - start_time)
    average_time = total_time / iterations
    return average_time
