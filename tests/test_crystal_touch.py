import pathlib
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

BOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))
import vos_bot


class StopAfterWaits(threading.Event):
    def __init__(self, count):
        super().__init__()
        self.remaining = count

    def wait(self, timeout=None):
        self.remaining -= 1
        if self.remaining <= 0:
            self.set()
        return self.is_set()


def make_overlay():
    overlay = vos_bot.AlignmentOverlay.__new__(vos_bot.AlignmentOverlay)
    overlay.lock = threading.Lock()
    overlay.crystal_match = (100, 20, 12, 12)
    overlay.crystal_score = .95
    overlay.crystal_generation = 1
    overlay.crystal_visible = True
    overlay.crystal_missing_frames = 0
    overlay.crystal_ignored_match = None
    overlay.crystal_ignored_missing_frames = 0
    return overlay


class CrystalTouchTests(unittest.TestCase):
    def test_touched_crystal_stays_hidden_until_missing_then_reappears(self):
        overlay = make_overlay()
        with patch.object(vos_bot, "log"):
            self.assertTrue(overlay.touch_crystal(1, (100, 20, 12, 12)))
            self.assertIsNone(overlay.crystal_match)
            for _ in range(5):
                overlay._update_crystal((101, 20, 12, 12), .96, 4)
                self.assertIsNone(overlay.crystal_match)
            overlay._update_crystal(None, 0, 4)
            overlay._update_crystal(None, 0, 4)
            self.assertIsNone(overlay.crystal_ignored_match)
            overlay._update_crystal((100, 20, 12, 12), .95, 4)
        self.assertEqual(overlay.crystal_match, (100, 20, 12, 12))
        self.assertEqual(overlay.crystal_generation, 2)

    def test_old_generation_cannot_hide_new_crystal(self):
        overlay = make_overlay()
        self.assertFalse(overlay.touch_crystal(0, (100, 20, 12, 12)))
        self.assertEqual(overlay.crystal_match, (100, 20, 12, 12))

    def test_crystal_line_uses_tight_contact_not_wide_happy_tolerance(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"auto_align_enabled": True, "auto_align_interval": .02,
            "alignment_checks_per_second": 10, "alignment_target_mode": "manual",
            "manual_anchor_offset": 0, "auto_align_tolerance_pixels": 200,
            "auto_align_key_hold": .001, "use_arduino": False, "loot_crystal": True}
        app.auto_align_stop = StopAfterWaits(2)
        app.input_lock = threading.Lock()
        app.spam_active = True
        app.spam_paused_reason = None
        app.alignment_move_pending = False
        app.auto_align_direction = "Idle"
        app.auto_align_delta = None
        app.auto_align_move_count = 0
        app.shop_controller = SimpleNamespace(state="idle")
        touched = []
        positions = iter(((100, 100, 20, 20), (250, 100, 20, 20)))
        app.alignment_overlay = SimpleNamespace(
            snapshot=lambda: ("Matched", (0, 0, 640, 480), next(positions), None,
                1.0, 0.0, time.monotonic(), (250, 20, 20, 20), .95, 1),
            touch_crystal=lambda generation, match: touched.append((generation, match)))
        moves = []
        with patch.object(vos_bot, "send_windows_direction",
                          side_effect=lambda direction, hold: moves.append(direction)):
            app._auto_align_loop()
        self.assertEqual(moves, ["RIGHT"])
        self.assertEqual(touched, [(1, (250, 20, 20, 20))])
        self.assertFalse(app.alignment_move_pending)


if __name__ == "__main__":
    unittest.main()
