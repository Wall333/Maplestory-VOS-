"""Inventory comparison and sequential shop workflow."""
import threading
import time


class ShopController:
    def __init__(self, app, api):
        self.app, self.api = app, api
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.state = "idle"
        self.test_cycle = False
        self.status = "Off"
        self.inventory_rect = None
        self.context = None
        self.changed = False
        self.matches = {}
        self.checked = 0.0
        self.next_action = 0.0
        self.shop_open_checked = 0.0
        self.shop_open_rect = None
        self.templates = {}
        self.cached_locations = {}
        self.cached_context = None
        self.thread = threading.Thread(target=self.detect_shared, daemon=True, name="shop-detector")

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=1)

    def reset(self):
        self.state = "idle"
        self.test_cycle = False
        self.next_action = 0.0

    def request_test(self):
        if self.state != "idle":
            return False
        self.test_cycle = True
        self.state = "open"
        self.next_action = 0.0
        return True

    def detect_shared(self):
        vision = self.app.vision
        names = ("inventory", "shop", "shop_open", "sell_button", "sell_confirm", "invent_empty", "shop_exit")
        for name in names:
            if name not in vision.templates:
                self.status = "Missing " + name + ".png"
                return
        self.templates = {name: vision.templates[name] for name in names}
        sequence, next_check = 0, 0.0
        try:
            while not self.stop_event.is_set():
                packet = vision.wait_next(sequence, .2)
                if packet is None:
                    continue
                sequence = packet.sequence
                now = packet.captured_at
                rate = max(1.0, min(30.0, float(self.app.config.get("inventory_checks_per_second", 5))))
                if now + .01 < next_check:
                    continue
                next_check = now + 1 / rate
                started = time.perf_counter()
                if not (self.app.config.get("shop_enabled") or self.app.config.get("inventory_debug")
                        or self.app.spam_active or self.test_cycle):
                    self.status = "Off"
                    continue
                context = packet.context
                if context is None:
                    with self.lock:
                        self.context = None
                        self.inventory_rect = None
                        self.changed = False
                        self.matches = {}
                    self.cached_locations.clear()
                    self.cached_context = None
                    self.shop_open_rect = None
                    self.shop_open_checked = 0.0
                    self.status = "Game inactive"
                    continue
                if context != self.cached_context:
                    self.cached_locations.clear()
                    self.cached_context = context
                    self.shop_open_rect = None
                    self.shop_open_checked = 0.0
                threshold = float(self.app.config.get("shop_match_threshold", .9))
                padding = int(self.app.config.get("vision_roi_padding", 120))
                shop_rate = max(.2, min(10.0, float(self.app.config.get("shop_open_checks_per_second", 1))))
                matches = {}
                futures = {}
                if now - self.shop_open_checked >= 1 / shop_rate:
                    self.shop_open_checked = now
                    futures["shop_open"] = vision.pool.submit(
                        vision.match, packet, "shop_open", threshold,
                        self.cached_locations.get("shop_open"), padding)
                elif self.shop_open_rect is not None:
                    matches["shop_open"] = self.shop_open_rect

                state = self.state
                if state == "idle":
                    needed = ()
                elif state == "open":
                    needed = ("shop",)
                elif state == "inspect":
                    needed = ("inventory", "invent_empty")
                elif state == "sell":
                    needed = ("sell_button", "sell_confirm")
                elif state == "confirm":
                    needed = ("sell_confirm", "invent_empty")
                else:
                    needed = ("shop_exit",)
                for name in needed:
                    futures[name] = vision.pool.submit(
                        vision.match, packet, name, threshold,
                        self.cached_locations.get(name), padding)
                futures["inventory_header"] = vision.pool.submit(
                    vision.match, packet, "inventory_header",
                    float(self.app.config.get("inventory_detection_threshold", .9)),
                    self.cached_locations.get("inventory_header"), padding)
                for name, future in futures.items():
                    rect, _ = future.result()
                    self.cached_locations[name] = rect
                    if name == "shop_open":
                        self.shop_open_rect = rect
                    if rect is not None:
                        matches[name] = rect

                inventory = self.templates["inventory"]
                ih, iw = inventory.shape[:2]
                header_rect = matches.pop("inventory_header", None)
                rect, changed = None, False
                if header_rect is not None:
                    x, y = header_rect[:2]
                    if y + ih <= packet.color.shape[0]:
                        roi = packet.color[y:y + ih, x:x + iw]
                        grid = inventory[40:ih - 30]
                        if grid.size:
                            grid_start = time.perf_counter()
                            similarity = float(self.api["cv2"].matchTemplate(
                                roi[40:ih - 30], grid, self.api["cv2"].TM_CCOEFF_NORMED)[0, 0])
                            vision.record("inventory_grid.local", time.perf_counter() - grid_start)
                            changed = similarity < float(self.app.config.get("inventory_match_threshold", .97))
                        rect = (x, y, iw, ih)
                with self.lock:
                    self.context, self.matches = context, matches
                    self.inventory_rect, self.changed = rect, changed
                    self.checked = time.monotonic()
                self.status = "Inventory changed" if changed else ("Inventory clean" if rect else "Inventory not detected")
                vision.record("cycle.shop", time.perf_counter() - started)
                vision.record("frame_age.shop", time.monotonic() - packet.captured_at)
        except Exception as exc:
            self.status = "Detector error: " + str(exc)


    def click(self, rect, context):
        if self.api["get_active_dreamms_context"]() != context or self.app.stop_event.is_set():
            return False
        x, y, w, h = rect
        left, top, _, _ = context[1]
        user32 = self.api["ctypes"].windll.user32
        user32.SetCursorPos(left + x + w // 2, top + y + h // 2)
        if self.app.config.get("use_arduino", True):
            return self.api["ARDUINO"].send_command(self.app.config, "CLICK", .03)
        user32.mouse_event(2, 0, 0, 0, 0)
        user32.mouse_event(4, 0, 0, 0, 0)
        return True

    def tick(self):
        """Called by the spam worker; return True while selling owns inputs."""
        auto_sell = bool(self.app.config.get("shop_enabled", False))
        with self.lock:
            context, changed, checked = self.context, self.changed, self.checked
            matches = dict(self.matches)
            inventory_rect = self.inventory_rect
        rate = max(1.0, min(30.0, float(self.app.config.get("inventory_checks_per_second", 5))))
        shop_rate = max(.2, min(10.0, float(self.app.config.get("shop_open_checks_per_second", 1))))
        max_age = max(.6, 2.0 / rate, 1.0 / shop_rate + .2)
        if self.state == "idle":
            if context is None or time.monotonic() - checked > max_age:
                return False
            if "shop_open" in matches:
                self.state = "inspect"
                self.api["log"]("Shop already open: checking inventory")
            elif changed and auto_sell:
                self.state = "open"
                self.api["log"]("Selling: inventory changed; opening shop")
            else:
                return False
        self.app.spam_paused_reason = "Selling: " + self.state
        if self.app.stop_event.is_set() or self.api["get_active_dreamms_context"]() != context:
            return True
        if context is None or time.monotonic() - checked > max_age or time.monotonic() < self.next_action:
            return True
        target = None
        if self.state == "inspect":
            if "shop_open" not in matches:
                self.reset()
                return False
            if "invent_empty" in matches or "inventory" in matches or (inventory_rect is not None and not changed):
                self.state = "exit"
                self.api["log"]("Shop open with clean/empty inventory: closing shop")
            elif changed:
                self.state = "sell" if auto_sell and self.app.config.get("shop_open_auto_sell", True) else "exit"
                self.api["log"]("Shop open with changed inventory: " + ("selling" if self.state == "sell" else "closing shop"))
        elif self.state == "open":
            if "shop_open" in matches:
                self.state = "sell"
            elif changed or self.test_cycle:
                target = matches.get("shop")
            else:
                self.reset()
                return False
        elif self.state == "sell":
            if "sell_confirm" in matches:
                self.state = "confirm"
            elif "shop_open" in matches:
                target = matches.get("sell_button")
        elif self.state == "confirm":
            if "sell_confirm" in matches:
                if self.app.config.get("use_arduino", True):
                    sent = self.api["ARDUINO"].send_key(self.app.config, "Y", .03)
                else:
                    self.api["send_windows_key"]("Y", .03)
                    sent = True
                if not sent:
                    self.app.stop_vos("Selling: confirmation key failed")
                self.next_action = time.monotonic() + 1
            elif "shop_open" in matches and "invent_empty" in matches:
                self.state = "exit"
        elif self.state == "exit":
            if "shop_open" not in matches:
                self.reset()
                self.api["log"]("Selling complete: shop closed")
                return False
            target = matches.get("shop_exit")
        if target is not None:
            if not self.click(target, context):
                self.app.stop_vos("Selling: click failed")
            self.next_action = time.monotonic() + 1
        return True
