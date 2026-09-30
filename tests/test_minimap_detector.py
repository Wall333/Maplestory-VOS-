import os
import sys
import unittest

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from minimap_detector import locate_minimap, marker_boxes, static_map_mask
from minimap_detector import MinimapDetector


class MinimapDetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = cv2.imread(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                               "assets", "minimap.png"))
        assert cls.template is not None
        cls.gray_template = cv2.cvtColor(cls.template, cv2.COLOR_BGR2GRAY)
        cls.mask = static_map_mask(cls.template)

    def frame_at(self, x, y):
        image = np.random.default_rng(8).integers(0, 60, (440, 750, 3), dtype=np.uint8)
        height, width = self.template.shape[:2]
        image[y:y + height, x:x + width] = self.template
        return image

    def test_sample_marker_count_and_player(self):
        image = self.frame_at(55, 30)
        height, width = self.template.shape[:2]
        reds, yellow = marker_boxes(image, (55, 30, width, height))
        self.assertEqual(len(reds), 1)
        self.assertIsNotNone(yellow)
        self.assertLess(reds[0][0], 55 + width)

    def test_detector_initializes_from_color_and_gray_templates(self):
        class Vision:
            templates = {"minimap": self.template}
            gray_templates = {"minimap": self.gray_template}

        class App:
            vision = Vision()

        detector = MinimapDetector(App(), lambda _: None)
        self.assertEqual(detector.mask.shape, self.gray_template.shape)
        self.assertGreater(np.count_nonzero(detector.mask), 0)

    def test_two_red_markers(self):
        image = self.frame_at(55, 30)
        height, width = self.template.shape[:2]
        cv2.rectangle(image, (55 + 89, 30 + 61), (55 + 93, 30 + 65), (0, 0, 255), -1)
        reds, yellow = marker_boxes(image, (55, 30, width, height))
        self.assertEqual(len(reds), 2)
        self.assertIsNotNone(yellow)

    def test_marker_movement_does_not_break_map_match(self):
        image = self.frame_at(55, 30)
        height, width = self.template.shape[:2]
        # Remove the original dots while retaining the stable map artwork.
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        moving = cv2.bitwise_or(cv2.inRange(hsv, (0, 90, 90), (10, 255, 255)),
                                cv2.inRange(hsv, (18, 90, 90), (40, 255, 255)))
        image = cv2.inpaint(image, moving, 2, cv2.INPAINT_TELEA)
        cv2.rectangle(image, (55 + 72, 30 + 60), (55 + 76, 30 + 64), (0, 0, 255), -1)
        cv2.rectangle(image, (55 + 65, 30 + 50), (55 + 69, 30 + 54), (0, 255, 255), -1)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        rect, score = locate_minimap(gray, self.gray_template, self.mask)
        self.assertEqual(rect, (55, 30, width, height))
        self.assertGreater(score, .93)
        reds, yellow = marker_boxes(image, rect)
        self.assertEqual(len(reds), 1)
        self.assertIsNotNone(yellow)

    def test_moved_minimap_falls_back_to_full_search(self):
        image = self.frame_at(490, 250)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        stages = []
        height, width = self.template.shape[:2]
        rect, score = locate_minimap(gray, self.gray_template, self.mask,
                                     cache=(55, 30, width, height), padding=40,
                                     timing=lambda stage, _: stages.append(stage))
        self.assertEqual(rect, (490, 250, width, height))
        self.assertGreater(score, .99)
        self.assertEqual(stages, ["minimap.local", "minimap.full"])

    def test_location_requires_yellow_player_marker(self):
        image = self.frame_at(55, 30)
        # A map-looking UI patch without the player marker is not a valid minimap.
        image[30 + 26:30 + 37, 55 + 49:55 + 60] = (25, 25, 25)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        rect, _ = locate_minimap(gray, self.gray_template, self.mask,
                                 threshold=.5, color=image)
        self.assertIsNone(rect)


if __name__ == "__main__":
    unittest.main()
