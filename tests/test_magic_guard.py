import pathlib
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

BOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))
import vos_bot
from vision_runtime import VisionRuntime


class MagicGuardTests(unittest.TestCase):
    def app(self, thorns=False):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"magic_guard_enabled": True, "magic_guard_key": "PGDN",
                      "magic_guard_wait_seconds": 5, "use_arduino": False,
                      "buff_enabled": thorns}
        app.buff_resume_not_before = 0
        app.input_lock = threading.Lock()
        app.spam_paused_reason = None
        app.shop_controller = SimpleNamespace(needs_attention=lambda: False)
        app.thorns_detector = SimpleNamespace(allows_spam=lambda: True)
        app.magic_guard_detector = SimpleNamespace(allows_spam=lambda: False)
        return app

    def test_cast_wait_and_resume_requires_detected_guard(self):
        app = self.app(thorns=True)
        with patch.object(vos_bot.time, "monotonic", return_value=10), \
             patch.object(vos_bot, "send_windows_key") as send, patch.object(vos_bot, "log"):
            self.assertTrue(app.maintain_buffs())
            send.assert_called_once_with("PGDN", .03)
            self.assertEqual(app.buff_resume_not_before, 15)
            self.assertIn("Magic Guard", app.spam_paused_reason)
            self.assertTrue(app.maintain_buffs())
            send.assert_called_once()
        app.magic_guard_detector.allows_spam = lambda: True
        with patch.object(vos_bot.time, "monotonic", return_value=16):
            self.assertFalse(app.maintain_buffs())

    def test_shop_priority_blocks_guard_key(self):
        app = self.app()
        app.shop_controller.needs_attention = lambda: True
        with patch.object(vos_bot, "send_windows_key") as send:
            self.assertTrue(app.maintain_buffs())
            send.assert_not_called()

    def test_missing_guard_retries_after_recovery(self):
        app = self.app()
        app.buff_resume_not_before = 15
        with patch.object(vos_bot.time, "monotonic", return_value=16), \
             patch.object(vos_bot, "send_windows_key") as send, patch.object(vos_bot, "log"):
            self.assertTrue(app.maintain_buffs())
            send.assert_called_once_with("PGDN", .03)

    def test_existing_asset_is_loaded_with_internal_guard_name(self):
        runtime = VisionRuntime(SimpleNamespace(config={}), str(BOT_DIR), lambda: None, lambda _: None)
        try:
            self.assertIn("magic_guard", runtime.templates)
            self.assertIn("magic_guard", runtime.gray_templates)
        finally:
            runtime.stop()
