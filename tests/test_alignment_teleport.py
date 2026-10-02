import pathlib
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import vos_bot as bot
from test_side_anchors import StopAfterWaits


class AlignmentTeleportTests(unittest.TestCase):
    def test_teleport_distance_and_limits_in_both_directions(self):
        config = {"auto_align_use_teleport": True}
        for character, target, allowed in ((200, 400, True), (400, 200, True),
                                            (200, 360, False), (480, 700, False)):
            with self.subTest(character=character, target=target):
                self.assertEqual(bot.alignment_teleport_allowed(config, character, target, 100, 600), allowed)
        self.assertFalse(bot.alignment_teleport_allowed({}, 200, 400, 100, 600))

    def test_arduino_holds_direction_around_teleport_key(self):
        device = bot.ArduinoConnection()
        events = []
        with patch.object(device, "send_command", side_effect=lambda cfg, cmd, hold: events.append(cmd) or True), \
             patch.object(bot.time, "sleep"):
            self.assertTrue(device.send_teleport({}, "LEFT", "ALT"))
        self.assertEqual(events, ["LEFT_DOWN", "ALT", "LEFT_UP"])

    def test_arduino_releases_direction_if_key_send_raises(self):
        device = bot.ArduinoConnection()
        with patch.object(device, "send_command", return_value=True) as command, \
             patch.object(device, "send_key", side_effect=RuntimeError("test failure")), \
             patch.object(bot.time, "sleep"):
            with self.assertRaises(RuntimeError):
                device.send_teleport({}, "RIGHT", "ALT")
            self.assertEqual(command.call_args.args[1], "RIGHT_UP")

    def test_windows_releases_direction_if_key_send_raises(self):
        with patch.object(bot, "set_windows_direction") as direction, \
             patch.object(bot, "send_windows_key", side_effect=RuntimeError("test failure")), \
             patch.object(bot.time, "sleep"):
            with self.assertRaises(RuntimeError):
                bot.send_windows_teleport("LEFT", "ALT")
            self.assertEqual(direction.call_args_list[-1].args, ("LEFT", False))

    def app(self, character, crystal=None):
        app = bot.VosApp.__new__(bot.VosApp)
        app.config = {**bot.DEFAULTS, "auto_align_randomize": False, "use_arduino": False,
                      "alignment_target_mode": "manual", "manual_anchor_offset": 0,
                      "auto_align_tolerance_pixels": 5, "auto_align_use_teleport": True}
        app.auto_align_stop = StopAfterWaits(3)
        app.input_lock = threading.Lock()
        app.spam_active = True
        app.spam_paused_reason = None
        app.alignment_move_pending = False
        app.auto_align_move_count = 0
        app.shop_controller = SimpleNamespace(state="idle", needs_attention=lambda: False)
        app.alignment_overlay = SimpleNamespace(
            character_captured_at=0,
            snapshot=lambda: ("Matched", (0, 0, 800, 600), (character - 10, 50, 20, 20),
                              None, 1, 0, time.monotonic(), crystal, 1, 1),
            touch_crystal=lambda *args: None)
        return app

    def test_teleport_requires_fresh_post_jump_frame_before_next_move(self):
        app = self.app(200)
        with patch.object(bot, "send_windows_teleport") as teleport, \
             patch.object(bot, "send_windows_direction") as walk:
            app._auto_align_loop()
        teleport.assert_called_once_with("RIGHT", "ALT")
        walk.assert_not_called()
        self.assertTrue(app.alignment_move_pending)

    def test_configurable_crystal_contact_changes_satisfaction(self):
        for tolerance, reached in ((15, True), (5, False)):
            app = self.app(100, (102, 50, 20, 20))
            app.config["crystal_contact_tolerance_pixels"] = tolerance
            app.auto_align_stop = StopAfterWaits(1)
            with patch.object(app.alignment_overlay, "touch_crystal") as touch, \
                 patch.object(bot, "send_windows_direction") as walk:
                app._auto_align_loop()
            self.assertEqual(touch.called, reached)
            self.assertEqual(walk.called, not reached)
