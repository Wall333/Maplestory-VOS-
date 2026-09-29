import pathlib
import sys
import unittest
from unittest.mock import mock_open, patch

BOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))
import vos_bot


class LogRoutingTests(unittest.TestCase):
    def test_activity_and_diagnostics_have_separate_buffers_and_files(self):
        vos_bot.LOG_BUFFER.clear()
        vos_bot.DIAGNOSTIC_LOG_BUFFER.clear()
        fake_file = mock_open()
        with patch("builtins.open", fake_file):
            vos_bot.log("Selling started")
            vos_bot.log("Yeti detected", diagnostic=True)
        self.assertEqual(len(vos_bot.LOG_BUFFER), 1)
        self.assertIn("Selling started", vos_bot.LOG_BUFFER[0])
        self.assertEqual(len(vos_bot.DIAGNOSTIC_LOG_BUFFER), 1)
        self.assertIn("Yeti detected", vos_bot.DIAGNOSTIC_LOG_BUFFER[0])
        opened_paths = [call.args[0] for call in fake_file.call_args_list]
        self.assertEqual(opened_paths, [vos_bot.LOG_PATH, vos_bot.ACTIVITY_LOG_PATH,
                                        vos_bot.LOG_PATH, vos_bot.DIAGNOSTIC_LOG_PATH])
        vos_bot.LOG_BUFFER.clear()
        vos_bot.DIAGNOSTIC_LOG_BUFFER.clear()


if __name__ == "__main__":
    unittest.main()
