# -*- coding: utf-8 -*-
"""Coordinate grid overlay for screenshots: makes tap positions readable.

Vertical grid lines + top labels give x; horizontal lines + left labels give y.
Screenshot pixels map 1:1 to /tap x y coordinates."""
import cv2

GRID_COLOR = (0, 230, 0)   # BGR: green grid lines
LABEL_BG = (0, 0, 0)
LABEL_FG = (0, 255, 0)


def annotate_coordinates(img, step: int = 100):
    """Return a copy of img with a coordinate grid and edge labels."""
    out = img.copy()
    h, w = out.shape[:2]

    for x in range(0, w, step):
        cv2.line(out, (x, 0), (x, h - 1), GRID_COLOR, 1)
    for y in range(0, h, step):
        cv2.line(out, (0, y), (w - 1, y), GRID_COLOR, 1)

    for x in range(0, w, step):
        _draw_label(out, str(x), (x + 3, 14))
    for y in range(0, h, step):
        _draw_label(out, str(y), (3, y + 14))

    return out


def _draw_label(img, text, pos):
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale, thickness = 0.4, 1
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    x, y = pos
    # Dark backing keeps labels readable over bright game art
    cv2.rectangle(img, (x - 2, y - th - 3), (x + tw + 2, y + 2), LABEL_BG, -1)
    cv2.putText(img, text, (x, y), font, scale, LABEL_FG, thickness, cv2.LINE_AA)
