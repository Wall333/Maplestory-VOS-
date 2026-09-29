import pathlib
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

BOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))

import vos_bot
from vision_runtime import Frame


class ShopTestIndependenceTests(unittest.TestCase):
    def test_map_uses_exact_cache_then_keeps_it_while_waiting(self):
        calls = []
        frames = [Frame(1, (1, (0, 0, 640, 480)), None, None, 1.0),
                  Frame(2, (1, (0, 0, 640, 480)), None, None, 1.2)]
        app = SimpleNamespace(config={"vos_map_checker_enabled": True,
            "vos_map_checks_per_second": 10, "vos_map_match_threshold": .6}, spam_active=True)
        detector = vos_bot.VosMapDetector(app)

        def wait_next(sequence, timeout):
            if sequence < len(frames):
                return frames[sequence]
            detector.stop_event.set()
            return None

        def match(frame, name, threshold, cache, padding):
            calls.append((cache, padding))
            return ((30, 40, 20, 20), .99) if len(calls) == 1 else (None, .3)

        with ThreadPoolExecutor(max_workers=1) as pool:
            app.vision = SimpleNamespace(templates={"VOS_map": object()}, pool=pool,
                wait_next=wait_next, match=match, record=lambda *args: None)
            with patch.object(vos_bot, "log"):
                detector._shared_loop()
        self.assertEqual(calls, [(None, 0), ((30, 40, 20, 20), 0)])
        self.assertEqual(detector.cached_location, (30, 40, 20, 20))
        self.assertEqual(detector.snapshot()[1], "Waiting for map")

    def test_manual_test_request_does_not_check_map_or_spammer(self):
        calls = []
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"shop_test_enabled": True}
        app.spam_active = False
        app.worker = None
        app.stop_event = threading.Event()
        app.shop_controller = SimpleNamespace(
            state="idle", request_test=lambda: calls.append("requested") or True)
        app.map_detector = SimpleNamespace(allows_spam=lambda: self.fail("map gate used"))
        with patch.object(vos_bot, "is_dreamms_active", return_value=True), \
             patch.object(vos_bot, "log"), \
             patch.object(threading.Thread, "start"):
            app.run_shop_test()
        self.assertEqual(calls, ["requested"])
        self.assertEqual(app.spam_paused_reason, "Selling: test")

    def test_map_loss_does_not_stop_spammer_or_manual_test(self):
        stopped = []
        test = SimpleNamespace(test_cycle=True)
        app = SimpleNamespace(spam_active=True, shop_controller=test,
            stop_vos=lambda reason: stopped.append(reason))
        detector = vos_bot.VosMapDetector(app)
        with patch.object(vos_bot, "log"):
            detector._set_state(False, "Not detected")
            self.assertEqual(stopped, [])
            test.test_cycle = False
            detector._set_state(False, "Not detected")
        self.assertEqual(stopped, [])

    def test_spam_worker_services_manual_test_before_map_gate(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"vos_hold": .03, "vos_interval": .1, "vos_output_key": "X"}
        app.stop_event = threading.Event()
        calls = []

        def shop_tick():
            calls.append("shop")
            app.stop_event.set()
            return True

        app.shop_controller = SimpleNamespace(test_cycle=True, tick=shop_tick)
        app.map_detector = SimpleNamespace(allows_spam=lambda: self.fail("map checked before shop test"))
        with patch.object(vos_bot, "is_dreamms_active", return_value=True):
            app._spam_loop()
        self.assertEqual(calls, ["shop"])

    def test_spam_worker_waits_for_missing_map_without_stopping(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"vos_hold": .03, "vos_interval": .1, "vos_output_key": "X"}
        app.stop_event = threading.Event()
        app.spam_active = True
        app.spam_paused_reason = None
        app.shop_controller = SimpleNamespace(test_cycle=False,
            tick=lambda: self.fail("shop checked while map missing"))

        def map_missing():
            app.stop_event.set()
            return False

        app.map_detector = SimpleNamespace(allows_spam=map_missing)
        with patch.object(vos_bot, "is_dreamms_active", return_value=True):
            app._spam_loop()
        self.assertTrue(app.spam_active)
        self.assertEqual(app.spam_paused_reason, "Waiting for map")


if __name__ == "__main__":
    unittest.main()
