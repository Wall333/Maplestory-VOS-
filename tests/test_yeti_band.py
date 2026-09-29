import pathlib
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

BOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))

import vos_bot
from vision_runtime import Frame, vertical_band_from_center


class YetiBandTests(unittest.TestCase):
    def test_center_relative_band_coordinates(self):
        self.assertEqual(vertical_band_from_center(1080, -200, 100), (340, 640))
        self.assertEqual(vertical_band_from_center(1080, -1000, 1000), (0, 1080))
        self.assertIsNone(vertical_band_from_center(1080, 100, -100))
        self.assertIsNone(vertical_band_from_center(1080, 900, 1000))

    def test_manual_band_never_requests_full_scan(self):
        frames = [Frame(i, (1, (0, 0, 640, 480)),
                        np.zeros((480, 640, 3), dtype=np.uint8), None, captured)
                  for i, captured in ((1, 1.0), (2, 3.2))]
        config = {"yeti_required": True, "show_yeti_overlay": True,
                  "yeti_checks_per_second": 10, "yeti_match_threshold": .8,
                  "monster_area_manual": True, "monster_area_top_offset": -100,
                  "monster_area_bottom_offset": 80,
                  "yeti_full_scan_interval_seconds": .2}
        app = SimpleNamespace(config=config)
        detector = vos_bot.YetiDetector(app)
        calls = []

        def wait_next(sequence, timeout):
            if sequence < len(frames):
                return frames[sequence]
            detector.stop_event.set()
            return None

        def match(frame, name, threshold, band, full):
            calls.append((band, full))
            return ((300, 200, 20, 20), .95) if name == "yeti" else (None, .2)

        with ThreadPoolExecutor(max_workers=3) as pool:
            app.vision = SimpleNamespace(templates={name: object() for name in
                ("yeti", "yeti2", "crown", "crown2")}, pool=pool,
                wait_next=wait_next, match_vertical_band=match, record=lambda *args: None)
            with patch.object(vos_bot, "log"):
                detector._shared_loop()
        self.assertEqual(len(calls), 8)
        self.assertTrue(all(band == (140, 320) and not full for band, full in calls))
        self.assertIsNone(detector.cached_band)
        self.assertEqual(detector.search_band_snapshot(480, frames[-1].context), (140, 320))

    def test_first_full_then_band_then_periodic_full_updates_height(self):
        frames = [Frame(i, (1, (0, 0, 640, 480)),
                        np.zeros((480, 640, 3), dtype=np.uint8), None, captured)
                  for i, captured in ((1, 1.0), (2, 1.2), (3, 3.1))]
        config = {"yeti_required": True, "show_yeti_overlay": True,
                  "yeti_checks_per_second": 10, "yeti_match_threshold": .8,
                  "yeti_band_padding_pixels": 40,
                  "yeti_full_scan_interval_seconds": 2.0}
        app = SimpleNamespace(config=config)
        detector = vos_bot.YetiDetector(app)
        calls = []
        call_lock = threading.Lock()

        def wait_next(sequence, timeout):
            if sequence < len(frames):
                return frames[sequence]
            detector.stop_event.set()
            return None

        def match(frame, name, threshold, band, full):
            with call_lock:
                calls.append((frame.sequence, name, band, full))
            if name == "yeti":
                return ((500, 300 if frame.sequence < 3 else 100, 20, 20), .95)
            return None, .2

        with ThreadPoolExecutor(max_workers=3) as pool:
            app.vision = SimpleNamespace(templates={name: object() for name in
                ("yeti", "yeti2", "crown", "crown2")}, pool=pool,
                wait_next=wait_next, match_vertical_band=match, record=lambda *args: None)
            with patch.object(vos_bot, "log"):
                detector._shared_loop()
        by_frame = {i: [call for call in calls if call[0] == i] for i in (1, 2, 3)}
        self.assertTrue(all(call[3] for call in by_frame[1]))
        self.assertTrue(all(not call[3] and call[2] == (260, 360) for call in by_frame[2]))
        self.assertTrue(all(call[3] for call in by_frame[3]))
        self.assertEqual(detector.cached_band, (60, 160))

    def test_missing_monster_does_not_full_scan_every_frame(self):
        frames = [Frame(i, (1, (0, 0, 640, 480)),
                        np.zeros((480, 640, 3), dtype=np.uint8), None, captured)
                  for i, captured in ((1, 1.0), (2, 1.2), (3, 3.1))]
        app = SimpleNamespace(config={"yeti_required": True, "show_yeti_overlay": True,
            "yeti_checks_per_second": 10, "yeti_full_scan_interval_seconds": 2.0})
        detector = vos_bot.YetiDetector(app)
        calls = []

        def wait_next(sequence, timeout):
            if sequence < len(frames):
                return frames[sequence]
            detector.stop_event.set()
            return None

        def match(frame, name, threshold, band, full):
            calls.append(frame.sequence)
            return None, .2

        with ThreadPoolExecutor(max_workers=3) as pool:
            app.vision = SimpleNamespace(templates={"yeti": object()}, pool=pool,
                wait_next=wait_next, match_vertical_band=match, record=lambda *args: None)
            with patch.object(vos_bot, "log"):
                detector._shared_loop()
        self.assertEqual(calls, [1, 3])
        self.assertIsNone(detector.cached_band)


if __name__ == "__main__":
    unittest.main()
