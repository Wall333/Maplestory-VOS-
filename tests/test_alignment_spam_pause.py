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


class AlignmentSpamPauseTests(unittest.TestCase):
    def test_spam_worker_pauses_skill_while_moving(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"vos_hold": .03, "vos_interval": .1, "vos_output_key": "Y",
            "use_arduino": False, "auto_align_enabled": True, "buff_enabled": False}
        app.stop_event = StopAfterWaits(1)
        app.input_lock = threading.Lock()
        app.spam_active = True
        app.alignment_move_pending = True
        app.spam_paused_reason = None
        app.shop_controller = SimpleNamespace(test_cycle=False, tick=lambda: False, needs_attention=lambda: False)
        app.map_detector = SimpleNamespace(allows_spam=lambda: True)
        app.yeti_detector = SimpleNamespace(allows_spam=lambda: self.fail("Yeti gate checked during movement"))
        with patch.object(vos_bot, "is_dreamms_active", return_value=True), \
             patch.object(vos_bot, "send_windows_key", side_effect=AssertionError("Skill sent during movement")):
            app._spam_loop()
        self.assertEqual(app.spam_paused_reason, "Moving")
        self.assertTrue(app.spam_active)

    def test_late_movement_request_still_blocks_skill_send(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"vos_hold": .03, "vos_interval": .1, "vos_output_key": "Y",
            "use_arduino": False, "auto_align_enabled": True, "buff_enabled": False}
        app.stop_event = StopAfterWaits(1)
        app.input_lock = threading.Lock()
        app.spam_active = True
        app.alignment_move_pending = False
        app.spam_paused_reason = None
        app.shop_controller = SimpleNamespace(test_cycle=False, tick=lambda: False, needs_attention=lambda: False)
        app.map_detector = SimpleNamespace(allows_spam=lambda: True)

        def gate_then_move():
            app.alignment_move_pending = True
            return True

        app.yeti_detector = SimpleNamespace(allows_spam=gate_then_move)
        with patch.object(vos_bot, "is_dreamms_active", return_value=True), \
             patch.object(vos_bot, "send_windows_key", side_effect=AssertionError("Skill sent during movement")):
            app._spam_loop()
        self.assertEqual(app.spam_paused_reason, "Moving")

    def test_skill_resumes_after_alignment_clears_pause(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"vos_hold": .03, "vos_interval": .1, "vos_output_key": "Y",
            "use_arduino": False, "auto_align_enabled": True, "buff_enabled": False}
        app.stop_event = threading.Event()
        app.input_lock = threading.Lock()
        app.spam_active = True
        app.alignment_move_pending = False
        app.spam_paused_reason = "Moving"
        app.send_count = 0
        app.shop_controller = SimpleNamespace(test_cycle=False, tick=lambda: False, needs_attention=lambda: False)
        app.map_detector = SimpleNamespace(allows_spam=lambda: True)
        app.yeti_detector = SimpleNamespace(allows_spam=lambda: True)
        sent = []

        def send_skill(key, hold):
            sent.append((key, hold))
            app.stop_event.set()

        with patch.object(vos_bot, "is_dreamms_active", return_value=True), \
             patch.object(vos_bot, "send_windows_key", side_effect=send_skill):
            app._spam_loop()
        self.assertEqual(sent, [("Y", .03)])
        self.assertEqual(app.send_count, 1)
        self.assertIsNone(app.spam_paused_reason)

    def test_movement_resumes_spam_only_after_fresh_alignment(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"auto_align_enabled": True, "auto_align_interval": .02,
            "alignment_checks_per_second": 10, "alignment_target_mode": "manual",
            "manual_anchor_offset": 0, "auto_align_tolerance_pixels": 20,
            "auto_align_key_hold": .001, "use_arduino": False, "loot_crystal": False}
        app.auto_align_stop = StopAfterWaits(2)
        app.input_lock = threading.Lock()
        app.spam_active = True
        app.spam_paused_reason = "Moving"
        app.alignment_move_pending = True
        app.auto_align_direction = "Idle"
        app.auto_align_delta = None
        app.auto_align_move_count = 0
        app.shop_controller = SimpleNamespace(state="idle", needs_attention=lambda: False)
        positions = iter(((0, 100, 20, 20), (310, 100, 20, 20)))
        app.alignment_overlay = SimpleNamespace(snapshot=lambda: (
            "Matched", (0, 0, 640, 480), next(positions), None,
            1.0, 0.0, time.monotonic(), None, 0.0, 0))
        movements = []
        with patch.object(vos_bot, "send_windows_direction",
                          side_effect=lambda direction, hold: movements.append((direction, hold))):
            app._auto_align_loop()
        self.assertEqual(movements, [("RIGHT", .001)])
        self.assertEqual(app.auto_align_move_count, 1)
        self.assertEqual(app.auto_align_direction, "Aligned")
        self.assertFalse(app.alignment_move_pending)
        self.assertIsNone(app.spam_paused_reason)

    def test_lost_character_marker_keeps_skill_paused(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"auto_align_enabled": True, "auto_align_interval": .02,
            "alignment_checks_per_second": 10}
        app.auto_align_stop = StopAfterWaits(1)
        app.spam_active = True
        app.spam_paused_reason = "Moving"
        app.alignment_move_pending = True
        app.auto_align_direction = "Idle"
        app.auto_align_delta = None
        app.shop_controller = SimpleNamespace(state="idle", needs_attention=lambda: False)
        app.alignment_overlay = SimpleNamespace(snapshot=lambda: (
            "Missing", (0, 0, 640, 480), None, None,
            0.0, 0.0, time.monotonic(), None, 0.0, 0))
        app._auto_align_loop()
        self.assertTrue(app.alignment_move_pending)
        self.assertEqual(app.spam_paused_reason, "Moving")
        self.assertEqual(app.auto_align_direction, "Waiting for character marker")

    def test_disabling_auto_alignment_releases_moving_pause(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"auto_align_enabled": True}
        app.auto_align_enabled = SimpleNamespace(get=lambda: False)
        app.alignment_move_pending = True
        app.spam_paused_reason = "Moving"
        app.auto_align_direction = "Moving RIGHT"
        app.auto_align_delta = -50
        with patch.object(vos_bot, "save_config"), patch.object(vos_bot, "log"):
            app.on_auto_align_changed()
        self.assertFalse(app.alignment_move_pending)
        self.assertIsNone(app.spam_paused_reason)
        self.assertEqual(app.auto_align_direction, "Off")


if __name__ == "__main__":
    unittest.main()
