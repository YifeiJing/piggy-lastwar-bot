# -*- coding: utf-8 -*-
from typing import Optional, Tuple, List
import cv2
import numpy as np


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
