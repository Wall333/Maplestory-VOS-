import pathlib
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

BOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))
import vos_bot


class FakeClockEvent:
    def __init__(self, stop_at):
        self.now = 10.0
        self.stop_at = stop_at
        self.stopped = False
        self.on_wait = None

    def is_set(self):
        return self.stopped

    def wait(self, seconds):
        if self.on_wait is not None:
            self.on_wait(self.now)
        self.now += seconds
        if self.now >= self.stop_at:
            self.stopped = True
        return self.stopped


class AlignmentRandomizerTests(unittest.TestCase):
    def test_sample_stays_inside_ranges(self):
        config = {"auto_align_random_tolerance_min_pixels": 12,
                  "auto_align_random_tolerance_max_pixels": 18,
                  "auto_align_random_delay_min_seconds": .2,
                  "auto_align_random_delay_max_seconds": .4}
        for _ in range(100):
            order = vos_bot.sample_alignment_move_order(config, 10, ("Area", 100))
            self.assertGreaterEqual(order.tolerance_pixels, 12)
            self.assertLessEqual(order.tolerance_pixels, 18)
            self.assertGreaterEqual(order.wait_seconds, .2)
            self.assertLessEqual(order.wait_seconds, .4)
            self.assertAlmostEqual(order.ready_at, 10 + order.wait_seconds)

    def test_spam_remains_unpaused_during_wait_then_movement_continues(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"auto_align_enabled": True, "auto_align_randomize": True,
            "auto_align_random_tolerance_min_pixels": 20,
            "auto_align_random_tolerance_max_pixels": 20,
            "auto_align_random_delay_min_seconds": .2,
            "auto_align_random_delay_max_seconds": .2,
            "auto_align_interval": .02, "alignment_checks_per_second": 10,
            "alignment_target_mode": "manual", "manual_anchor_offset": 0,
            "auto_align_key_hold": .001, "use_arduino": False, "loot_crystal": False}
        clock = FakeClockEvent(10.31)
        app.auto_align_stop = clock
        app.input_lock = threading.Lock()
        app.spam_active = True
        app.spam_paused_reason = None
        app.alignment_move_pending = False
        app.auto_align_direction = "Idle"
        app.auto_align_delta = None
        app.auto_align_move_count = 0
        app.shop_controller = SimpleNamespace(state="idle")
        app._reset_alignment_randomizer()
        app.alignment_overlay = SimpleNamespace(snapshot=lambda: (
            "Matched", (0, 0, 640, 480), (100, 100, 20, 20), None,
            1.0, 0.0, clock.now, None, 0.0, 0))
        moves = []
        preparation_states = []
        clock.on_wait = lambda now: preparation_states.append(
            (now, app.alignment_move_pending, app.spam_paused_reason)) if now < 10.2 else None
        with patch.object(vos_bot.time, "monotonic", side_effect=lambda: clock.now), \
             patch.object(vos_bot, "send_windows_direction",
                          side_effect=lambda direction, hold: moves.append((clock.now, direction))):
            app._auto_align_loop()
        self.assertGreater(len(moves), 1)
        self.assertGreaterEqual(moves[0][0], 10.2)
        self.assertEqual(moves[0][1], "RIGHT")
        self.assertLess(moves[1][0] - moves[0][0], .2)
        self.assertTrue(preparation_states)
        self.assertTrue(all(not moving and reason != "Moving"
                            for _, moving, reason in preparation_states))
        self.assertTrue(app.alignment_move_pending)
        self.assertEqual(app.spam_paused_reason, "Moving")

    def test_alignment_during_wait_cancels_order(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"auto_align_enabled": True, "auto_align_randomize": True,
            "auto_align_random_tolerance_min_pixels": 20,
            "auto_align_random_tolerance_max_pixels": 20,
            "auto_align_random_delay_min_seconds": .2,
            "auto_align_random_delay_max_seconds": .2,
            "auto_align_interval": .02, "alignment_checks_per_second": 10,
            "alignment_target_mode": "manual", "manual_anchor_offset": 0,
            "auto_align_key_hold": .001, "use_arduino": False, "loot_crystal": False}
        clock = FakeClockEvent(10.31)
        app.auto_align_stop = clock
        app.input_lock = threading.Lock()
        app.spam_active = True
        app.spam_paused_reason = None
        app.alignment_move_pending = False
        app.auto_align_direction = "Idle"
        app.auto_align_delta = None
        app.auto_align_move_count = 0
        app.shop_controller = SimpleNamespace(state="idle")
        app._reset_alignment_randomizer()
        app.alignment_overlay = SimpleNamespace(snapshot=lambda: (
            "Matched", (0, 0, 640, 480),
            (100, 100, 20, 20) if clock.now < 10.1 else (310, 100, 20, 20),
            None, 1.0, 0.0, clock.now, None, 0.0, 0))
        with patch.object(vos_bot.time, "monotonic", side_effect=lambda: clock.now), \
             patch.object(vos_bot, "send_windows_direction",
                          side_effect=AssertionError("Move sent after alignment")):
            app._auto_align_loop()
        self.assertFalse(app.alignment_move_pending)
        self.assertIsNone(app.spam_paused_reason)
        self.assertIsNone(app.auto_align_move_order)


if __name__ == "__main__":
    unittest.main()
