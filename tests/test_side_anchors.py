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


class SideAnchorTests(unittest.TestCase):
    def test_hiding_guides_keeps_movement_limits(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"side_anchor_left_percent": 27,
                      "side_anchor_right_percent": 73,
                      "show_side_anchors": True}
        app.show_side_anchors = SimpleNamespace(get=lambda: False)
        with patch.object(vos_bot, "save_config") as save, patch.object(vos_bot, "log"):
            app.on_show_side_anchors_changed()
        self.assertFalse(app.config["show_side_anchors"])
        self.assertEqual(vos_bot.side_anchor_bounds(app.config, 1001), (270, 730))
        save.assert_called_once_with(app.config)

    def test_bounds_scale_with_client_width(self):
        config = {"side_anchor_left_percent": 25, "side_anchor_right_percent": 75}
        self.assertEqual(vos_bot.side_anchor_bounds(config, 1001), (250, 750))
        self.assertEqual(vos_bot.side_anchor_bounds({}, 640), (0, 639))

    def test_outside_side_anchor_is_not_happy_even_with_wide_tolerance(self):
        self.assertFalse(vos_bot.alignment_goal_met(94, 110, 200, 100, 200))
        self.assertTrue(vos_bot.alignment_goal_met(102, 110, 200, 100, 200))

    def assert_crystal_reached_at_limit(self, first_center, limit_center, crystal_center, expected_direction):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"auto_align_enabled": True, "auto_align_interval": .02,
            "alignment_checks_per_second": 10, "alignment_target_mode": "manual",
            "manual_anchor_offset": 0, "auto_align_tolerance_pixels": 200,
            "auto_align_key_hold": .001, "use_arduino": False, "loot_crystal": True,
            "side_anchor_left_percent": 25, "side_anchor_right_percent": 75}
        app.auto_align_stop = StopAfterWaits(2)
        app.input_lock = threading.Lock()
        app.spam_active = True
        app.spam_paused_reason = None
        app.alignment_move_pending = False
        app.auto_align_direction = "Idle"
        app.auto_align_delta = None
        app.auto_align_move_count = 0
        app.shop_controller = SimpleNamespace(state="idle", needs_attention=lambda: False)
        positions = iter((first_center, limit_center))
        crystal = (crystal_center - 10, 20, 20, 20)
        touched, movements = [], []
        app.alignment_overlay = SimpleNamespace(
            snapshot=lambda: ("Matched", (0, 0, 640, 480),
                (next(positions) - 10, 100, 20, 20), None,
                1.0, 0.0, time.monotonic(), crystal, .95, 1),
            touch_crystal=lambda generation, match: touched.append((generation, match)))
        with patch.object(vos_bot, "send_windows_direction",
                          side_effect=lambda direction, hold: movements.append(direction)):
            app._auto_align_loop()
        self.assertEqual(movements, [expected_direction])
        self.assertEqual(touched, [(1, crystal)])
        self.assertEqual(app.auto_align_direction, "Crystal side limit reached")
        self.assertFalse(app.alignment_move_pending)

    def test_crystal_beyond_right_limit_stops_at_right_anchor(self):
        self.assert_crystal_reached_at_limit(300, 479, 610, "RIGHT")

    def test_crystal_beyond_left_limit_stops_at_left_anchor(self):
        self.assert_crystal_reached_at_limit(400, 160, 40, "LEFT")


if __name__ == "__main__":
    unittest.main()
