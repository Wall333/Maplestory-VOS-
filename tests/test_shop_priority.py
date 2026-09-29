import pathlib
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

BOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))
import vos_bot
from shop_controller import ShopController


class ShopPriorityTests(unittest.TestCase):
    def make_controller(self):
        clock = SimpleNamespace(now=10.0)
        context = (1, (0, 0, 640, 480))
        messages = []
        keys = []
        app = SimpleNamespace(
            config={"shop_enabled": True, "use_arduino": False,
                    "inventory_checks_per_second": 5,
                    "shop_open_checks_per_second": 1},
            spam_active=True, stop_event=threading.Event(), spam_paused_reason=None,
            stop_vos=lambda reason: self.fail(f"Unexpected shop stop: {reason}"))
        api = {"log": messages.append, "send_windows_key": lambda *args: keys.append(args),
               "get_active_dreamms_context": lambda: context}
        controller = ShopController(app, api)
        controller.context = context
        controller.checked = clock.now
        controller.inventory_rect = (10, 10, 100, 100)
        controller.changed = True
        controller.click = lambda rect, ctx: True
        return clock, app, controller, messages, keys

    def test_sale_stays_latched_if_inventory_detection_flickers_clean(self):
        clock, app, shop, messages, _ = self.make_controller()
        with patch("shop_controller.time.monotonic", side_effect=lambda: clock.now):
            shop.changed_pending = True
            self.assertTrue(shop.needs_attention())
            self.assertTrue(shop.tick())
            self.assertEqual(shop.state, "open")
            shop.changed = False
            shop.matches = {}
            self.assertTrue(shop.tick())
            self.assertEqual(shop.state, "open")
            self.assertEqual(len([m for m in messages if "opening shop" in m]), 1)

    def test_confirmation_exits_without_invent_empty_then_rechecks(self):
        clock, app, shop, messages, keys = self.make_controller()
        shop.state = "confirm"
        shop.matches = {"shop_open": (1, 1, 5, 5), "sell_confirm": (2, 2, 5, 5)}
        with patch("shop_controller.time.monotonic", side_effect=lambda: clock.now):
            self.assertTrue(shop.tick())
            self.assertEqual(keys, [("Y", .03)])
            clock.now += 1.1
            shop.checked = clock.now
            shop.matches = {"shop_open": (1, 1, 5, 5)}
            self.assertTrue(shop.tick())
            self.assertEqual(shop.state, "exit")
            shop.matches["shop_exit"] = (4, 4, 5, 5)
            self.assertTrue(shop.tick())
            clock.now += 1.1
            shop.checked = clock.now
            shop.matches = {}
            self.assertTrue(shop.tick())
            self.assertEqual(shop.state, "recheck")
            self.assertTrue(shop.needs_attention())
            clock.now += .6
            shop.checked = clock.now
            shop.changed = True
            self.assertTrue(shop.tick())
            self.assertEqual(shop.state, "open")
            self.assertTrue(any("retrying" in message for message in messages))

    def test_clean_recheck_releases_shop_ownership(self):
        clock, app, shop, messages, _ = self.make_controller()
        shop.state = "recheck"
        shop.recheck_after = 9.0
        shop.changed = False
        shop.matches = {}
        with patch("shop_controller.time.monotonic", side_effect=lambda: clock.now):
            self.assertTrue(shop.tick())
            self.assertEqual(shop.state, "recheck")
            clock.now += .2
            shop.checked = clock.now
            self.assertFalse(shop.tick())
        self.assertEqual(shop.state, "idle")
        self.assertTrue(any("inventory clean" in message for message in messages))

    def test_pending_inventory_change_blocks_skill_send(self):
        app = vos_bot.VosApp.__new__(vos_bot.VosApp)
        app.config = {"vos_hold": .03, "vos_interval": .1, "vos_output_key": "F",
                      "auto_align_enabled": False, "buff_enabled": False}
        app.input_lock = threading.Lock()
        app.stop_event = threading.Event()
        app.spam_paused_reason = None
        app.shop_controller = SimpleNamespace(
            tick=lambda: False, needs_attention=lambda: app.stop_event.set() or True)
        app.map_detector = SimpleNamespace(allows_spam=lambda: True)
        app.yeti_detector = SimpleNamespace(allows_spam=lambda: self.fail("Monster gate checked before sale"))
        with patch.object(vos_bot, "is_dreamms_active", return_value=True), \
             patch.object(vos_bot, "send_windows_key", side_effect=AssertionError("Skill sent before sale")):
            app._spam_loop()


if __name__ == "__main__":
    unittest.main()
