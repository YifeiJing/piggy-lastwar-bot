# -*- coding: utf-8 -*-
"""Tests for the screenshot coordinate-grid overlay."""
import unittest

import numpy as np

from vision.annotate import GRID_COLOR, LABEL_BG, LABEL_FG, annotate_coordinates


class TestAnnotateCoordinates(unittest.TestCase):
    def _noise(self, h=1600, w=900):
        return np.random.RandomState(1).randint(0, 256, (h, w, 3), dtype=np.uint8)

    def test_grid_lines_drawn_at_expected_positions(self):
        img = self._noise()
        out = annotate_coordinates(img)
        # vertical line at x=300, horizontal line at y=500
        self.assertTrue(np.array_equal(out[500, 300], GRID_COLOR))
        self.assertTrue(np.array_equal(out[500, 600], GRID_COLOR))
        self.assertTrue(np.array_equal(out[900, 300], GRID_COLOR))

    def test_labels_drawn_in_corner(self):
        out = annotate_coordinates(self._noise())
        corner = out[0:20, 0:30]
        self.assertTrue(np.any(np.all(corner == LABEL_FG, axis=2)))
        self.assertTrue(np.any(np.all(corner == LABEL_BG, axis=2)))

    def test_input_not_mutated_and_shape_preserved(self):
        img = self._noise(h=400, w=300)
        original = img.copy()
        out = annotate_coordinates(img)
        self.assertEqual(out.shape, img.shape)
        self.assertTrue(np.array_equal(img, original))


if __name__ == '__main__':
    unittest.main()
