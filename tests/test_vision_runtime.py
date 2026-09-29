import pathlib
import sys
import threading
import time
import unittest
from types import SimpleNamespace

import cv2
import numpy as np

BOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))

from vision_runtime import Frame, VisionRuntime
from vos_bot import AlignmentOverlay


class DummyApp:
    config = {"vos_map_checks_per_second": 10, "alignment_checks_per_second": 10}
    spam_active = False


class VisionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime = VisionRuntime(DummyApp(), str(BOT_DIR),
                                     lambda: (1, (0, 0, 640, 480)), lambda message: None)

    def tearDown(self):
        self.runtime.stop()

    def frame_with(self, name, x, y, sequence=1):
        template = self.runtime.templates[name]
        height, width = template.shape[:2]
        color = np.random.default_rng(sequence).integers(0, 80, (480, 640, 3), dtype=np.uint8)
        color[y:y + height, x:x + width] = template
        return Frame(sequence, (1, (0, 0, 640, 480)), color,
                     cv2.cvtColor(color, cv2.COLOR_BGR2GRAY), time.monotonic())

    def test_moving_template_uses_immediate_full_fallback(self):
        first = self.frame_with("thorns", 20, 25)
        old_rect, _ = self.runtime.match(first, "thorns", .95, padding=30)
        self.assertEqual(old_rect[:2], (20, 25))
        moved = self.frame_with("thorns", 420, 260, 2)
        new_rect, _ = self.runtime.match(moved, "thorns", .95, old_rect, 30)
        self.assertEqual(new_rect[:2], (420, 260))
        self.assertIn("thorns.local", self.runtime.summary())
        self.assertIn("thorns.full", self.runtime.summary())

    def test_map_exact_cache_and_full_reacquisition(self):
        first = self.frame_with("VOS_map", 30, 40)
        old_rect, _ = self.runtime.match(first, "VOS_map", .95)
        same_rect, _ = self.runtime.match(first, "VOS_map", .95, old_rect, 0)
        self.assertEqual(same_rect, old_rect)
        moved = self.frame_with("VOS_map", 350, 260, 2)
        new_rect, _ = self.runtime.match(moved, "VOS_map", .95, old_rect, 0)
        self.assertEqual(new_rect[:2], (350, 260))
        self.assertIn("VOS_map.local", self.runtime.summary())
        self.assertIn("VOS_map.full", self.runtime.summary())

    def test_monster_band_covers_full_width_and_periodic_full_finds_new_height(self):
        first = self.frame_with("yeti", 500, 300)
        rect, _ = self.runtime.match_vertical_band(first, "yeti", .95, (260, 400))
        self.assertEqual(rect[:2], (500, 300))
        moved = self.frame_with("yeti", 500, 50, 2)
        rect, _ = self.runtime.match_vertical_band(moved, "yeti", .95, (260, 400))
        self.assertIsNone(rect)
        rect, _ = self.runtime.match_vertical_band(moved, "yeti", .95, (260, 400), full=True)
        self.assertEqual(rect[:2], (500, 50))
        self.assertIn("yeti.band", self.runtime.summary())
        self.assertIn("yeti.full", self.runtime.summary())

    def test_moving_arrows_use_full_fallback(self):
        arrow = cv2.imread(str(BOT_DIR / "assets" / "tracker.png"))
        height, width = arrow.shape[:2]
        color = np.full((480, 640, 3), (80, 70, 120), dtype=np.uint8)
        color[300:300 + height, 500:500 + width] = arrow
        frame = Frame(1, (1, (0, 0, 640, 480)), color,
                      cv2.cvtColor(color, cv2.COLOR_BGR2GRAY), time.monotonic())
        rect, _ = self.runtime.match_arrow(frame, .6, (10, 10, width, height), 30)
        self.assertIsNotNone(rect)
        self.assertLessEqual(abs(rect[0] - 500), 1)
        self.assertLessEqual(abs(rect[1] - 300), 1)
        self.assertIn("arrows.local", self.runtime.summary())
        self.assertIn("arrows.full", self.runtime.summary())

    def test_one_capture_publishes_shared_color_and_gray(self):
        import vision_runtime

        runtime = self.runtime

        class FakeCapture:
            calls = 0

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def grab(self, bounds):
                self.calls += 1
                runtime.stop_event.set()
                return np.zeros((480, 640, 4), dtype=np.uint8)

        fake = FakeCapture()
        original = vision_runtime.mss.mss
        vision_runtime.mss.mss = lambda: fake
        try:
            runtime._capture_loop()
        finally:
            vision_runtime.mss.mss = original
        self.assertEqual(fake.calls, 1)
        self.assertEqual(runtime.frame.sequence, 1)
        self.assertEqual(runtime.frame.color.shape, (480, 640, 3))
        self.assertEqual(runtime.frame.gray.shape, (480, 640))

    def test_character_worker_is_not_blocked_by_general_matches(self):
        release = threading.Event()
        occupied = threading.Barrier(4)

        def block_general():
            occupied.wait(timeout=3)
            release.wait(timeout=3)

        futures = [self.runtime.pool.submit(block_general) for _ in range(3)]
        try:
            occupied.wait(timeout=3)
            result = self.runtime.submit_character(lambda: "tracked")
            self.assertEqual(result.result(timeout=1), "tracked")
            self.assertIn("character.queue", self.runtime.summary())
            self.assertIn("character.match", self.runtime.summary())
        finally:
            release.set()
            for future in futures:
                future.result(timeout=3)

    def test_target_result_does_not_replace_newer_character_result(self):
        overlay = AlignmentOverlay.__new__(AlignmentOverlay)
        overlay.app = SimpleNamespace(config={"alignment_overlay_enabled": True,
            "auto_align_enabled": False, "alignment_target_mode": "area",
            "character_tracker_mode": "arrows"})
        overlay.lock = threading.Lock()
        overlay.context_sequence = -1
        overlay.hwnd = overlay.client_bbox = None
        overlay.bulb_match = overlay.area_match = overlay.crystal_match = None
        overlay.bulb_score = overlay.area_score = overlay.crystal_score = 0.0
        overlay.crystal_visible = False
        overlay.crystal_generation = 0
        overlay.crystal_missing_frames = 0
        overlay.last_check = 0.0
        overlay.status = "Off"
        context = (1, (0, 0, 640, 480))
        self.assertTrue(overlay._ensure_context(Frame(1, context, None, None, 0)))
        with overlay.lock:
            overlay.bulb_match = (200, 100, 20, 20)
            overlay.area_match = (300, 100, 20, 20)
            overlay._refresh_match_status_locked()
        self.assertEqual(overlay.snapshot()[2:4], ((200, 100, 20, 20), (300, 100, 20, 20)))
        self.assertEqual(overlay.snapshot()[0], "Both matched")
        new_context = (2, (0, 0, 640, 480))
        self.assertTrue(overlay._ensure_context(Frame(3, new_context, None, None, 0)))
        self.assertFalse(overlay._ensure_context(Frame(2, context, None, None, 0)))
        self.assertIsNone(overlay.snapshot()[2])
        self.assertIsNone(overlay.snapshot()[3])


if __name__ == "__main__":
    unittest.main()
