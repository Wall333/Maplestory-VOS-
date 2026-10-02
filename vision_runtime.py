"""One DreamMS capture stream, shared templates, bounded matching and timings."""

from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import os
import threading
import time

import cv2
import mss
import numpy as np
from arrow_tracker import ArrowShapeTracker


TEMPLATE_NAMES = (
    "VOS_map", "yeti", "yeti2", "crown", "crown2", "thorns", "magic_guard", "lightbulb",
    "area", "crystal", "inventory", "shop", "shop_open", "sell_button",
    "sell_confirm", "invent_empty", "shop_exit", "minimap",
)


@dataclass(frozen=True)
class Frame:
    sequence: int
    context: tuple | None
    color: np.ndarray | None
    gray: np.ndarray | None
    captured_at: float


def vertical_band_from_center(height, top_offset, bottom_offset):
    """Return a client-relative [top, bottom) band from centre-based offsets."""
    if height <= 0 or top_offset >= bottom_offset:
        return None
    center = height // 2
    top = max(0, min(height, center + int(top_offset)))
    bottom = max(0, min(height, center + int(bottom_offset)))
    return (top, bottom) if top < bottom else None


class VisionRuntime:
    def __init__(self, app, base_dir, context_fn, log_fn, workers=3):
        self.app = app
        self.context_fn = context_fn
        self.log_fn = log_fn
        self.templates = {}
        self.gray_templates = {}
        for name in TEMPLATE_NAMES:
            filename = "magic guard" if name == "magic_guard" else name
            image = cv2.imread(os.path.join(base_dir, "assets", filename + ".png"), cv2.IMREAD_COLOR)
            if image is not None and image.size:
                self.templates[name] = image
                self.gray_templates[name] = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if "inventory" in self.templates:
            self.templates["inventory_header"] = self.templates["inventory"][:35]
            self.gray_templates["inventory_header"] = self.gray_templates["inventory"][:35]
        try:
            self.arrow_tracker = ArrowShapeTracker(os.path.join(base_dir, "assets", "tracker.png"))
        except ValueError as exc:
            self.arrow_tracker = None
            log_fn(f"Arrow tracker unavailable: {exc}")
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vision-match")
        # Keep character tracking out of the general detector queue. It is
        # latency-sensitive; map/shop/monster reacquisition can occupy every
        # general worker for hundreds of milliseconds.
        self.character_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vision-character")
        self.condition = threading.Condition()
        self.frame = Frame(0, None, None, None, 0.0)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._capture_loop, name="dreamms-capture", daemon=True)
        self.perf_lock = threading.Lock()
        self.timings = defaultdict(lambda: deque(maxlen=120))
        self.last_frame_at = None

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        with self.condition:
            self.condition.notify_all()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.character_pool.shutdown(wait=False, cancel_futures=True)

    def submit_character(self, fn, *args):
        submitted = time.perf_counter()

        def run():
            self.record("character.queue", time.perf_counter() - submitted)
            started = time.perf_counter()
            try:
                return fn(*args)
            finally:
                self.record("character.match", time.perf_counter() - started)

        return self.character_pool.submit(run)

    def record(self, name, elapsed):
        with self.perf_lock:
            self.timings[name].append(elapsed * 1000)

    def summary(self):
        with self.perf_lock:
            return {name: (sum(values) / len(values), max(values))
                    for name, values in self.timings.items() if values}

    def _capture_rate(self):
        config = self.app.config
        rates = []
        if config.get("vos_map_checker_enabled", True):
            rates.append(float(config.get("vos_map_checks_per_second", 10)))
        if config.get("yeti_required") or config.get("show_yeti_overlay") or config.get("show_monster_area"):
            rates.append(float(config.get("yeti_checks_per_second", 10)))
        if config.get("buff_enabled"):
            rates.append(float(config.get("thorns_checks_per_second", 2)))
        if config.get("magic_guard_enabled"):
            rates.append(float(config.get("magic_guard_checks_per_second", 2)))
        if config.get("minimap_checker_enabled"):
            rates.append(float(config.get("minimap_checks_per_second", 5)))
        if any(config.get(name, False) for name in (
            "alignment_overlay_enabled", "auto_align_enabled", "show_spammer_overlay", "show_latency_overlay", "show_crystal"
        )):
            rates.append(float(config.get("alignment_checks_per_second", 10)))
        shop_controller = getattr(self.app, "shop_controller", None)
        if (config.get("shop_enabled") or config.get("inventory_debug") or self.app.spam_active
                or (shop_controller is not None and shop_controller.test_cycle)):
            rates.append(float(config.get("inventory_checks_per_second", 5)))
        return max(1.0, min(100.0, max(rates, default=1.0)))

    def _publish(self, context, color, gray, captured_at):
        with self.condition:
            self.frame = Frame(self.frame.sequence + 1, context, color, gray, captured_at)
            self.condition.notify_all()

    def _capture_loop(self):
        last_log = time.monotonic()
        try:
            with mss.mss() as sct:
                while not self.stop_event.is_set():
                    started = time.perf_counter()
                    context = self.context_fn()
                    if context is None:
                        self.last_frame_at = None
                        if self.frame.context is not None or self.frame.sequence == 0:
                            self._publish(None, None, None, time.monotonic())
                        self.stop_event.wait(.1)
                        continue
                    left, top, right, bottom = context[1]
                    if right <= left or bottom <= top:
                        self.stop_event.wait(.1)
                        continue
                    shot = sct.grab({"left": left, "top": top,
                                     "width": right - left, "height": bottom - top})
                    # One contiguous BGR conversion is cheaper than making
                    # every color matcher repack a strided BGRA view.
                    color = cv2.cvtColor(np.asarray(shot, dtype=np.uint8), cv2.COLOR_BGRA2BGR)
                    capture_end = time.perf_counter()
                    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
                    preprocess_end = time.perf_counter()
                    self.record("capture", capture_end - started)
                    self.record("grayscale", preprocess_end - capture_end)
                    self.record("cycle.frame", preprocess_end - started)
                    now = time.monotonic()
                    if self.last_frame_at is not None:
                        self.record("capture_interval", now - self.last_frame_at)
                    self.last_frame_at = now
                    self._publish(context, color, gray, now)
                    if now - last_log >= 30:
                        values = self.summary()
                        details = ", ".join(f"{name} avg={avg:.1f} max={high:.1f}ms"
                                            for name, (avg, high) in sorted(values.items()))
                        self.log_fn("Vision perf (last 120): " + details)
                        last_log = now
                    self.stop_event.wait(max(0.0, 1 / self._capture_rate()
                                             - (time.perf_counter() - started)))
        except Exception as exc:
            self.log_fn(f"Vision capture error: {exc}")
            self._publish(None, None, None, time.monotonic())

    def wait_next(self, sequence, timeout=.5):
        with self.condition:
            if self.frame.sequence <= sequence and not self.stop_event.is_set():
                self.condition.wait(timeout)
            return self.frame if self.frame.sequence > sequence else None

    def match(self, frame, name, threshold, cache=None, padding=120, grayscale=False):
        """Padded local attempt, immediately followed by full-frame reacquisition."""
        start = time.perf_counter()
        image = frame.gray if grayscale else frame.color
        template = (self.gray_templates if grayscale else self.templates).get(name)
        if image is None or template is None:
            return None, 0.0
        height, width = template.shape[:2]
        if image.shape[0] < height or image.shape[1] < width:
            return None, 0.0

        def search(roi, left, top, stage):
            stage_start = time.perf_counter()
            result = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, location = cv2.minMaxLoc(result)
            self.record(f"{name}.{stage}", time.perf_counter() - stage_start)
            return (left + location[0], top + location[1], width, height), float(score)

        if cache is not None:
            x, y, _, _ = cache
            left = max(0, x - padding)
            top = max(0, y - padding)
            right = min(image.shape[1], x + width + padding)
            bottom = min(image.shape[0], y + height + padding)
            if right - left >= width and bottom - top >= height:
                rect, score = search(image[top:bottom, left:right], left, top, "local")
                if score >= threshold:
                    self.record(f"{name}.total", time.perf_counter() - start)
                    return rect, score
        rect, score = search(image, 0, 0, "full")
        self.record(f"{name}.total", time.perf_counter() - start)
        return (rect if score >= threshold else None), score

    def match_vertical_band(self, frame, name, threshold, band=None, full=False):
        """Search a full-width vertical band, or the full frame when scheduled."""
        started = time.perf_counter()
        image = frame.color
        template = self.templates.get(name)
        if image is None or template is None or (band is None and not full):
            return None, 0.0
        height, width = template.shape[:2]
        if full:
            top, bottom = 0, image.shape[0]
            stage = "full"
        else:
            top = max(0, int(band[0]))
            bottom = min(image.shape[0], int(band[1]))
            stage = "band"
        if bottom - top < height or image.shape[1] < width:
            return None, 0.0
        match_started = time.perf_counter()
        result = cv2.matchTemplate(image[top:bottom], template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        self.record(f"{name}.{stage}", time.perf_counter() - match_started)
        self.record(f"{name}.total", time.perf_counter() - started)
        rect = (location[0], top + location[1], width, height)
        return (rect if score >= threshold else None), float(score)

    def match_arrow(self, frame, threshold, cache=None, padding=120):
        start = time.perf_counter()
        gray = frame.gray
        if gray is None or self.arrow_tracker is None:
            return None, 0.0
        tracker = self.arrow_tracker
        if cache is not None:
            x, y, _, _ = cache
            left = max(0, x - padding)
            top = max(0, y - padding)
            right = min(gray.shape[1], x + tracker.width + padding)
            bottom = min(gray.shape[0], y + tracker.height + padding)
            local_start = time.perf_counter()
            rect, score = tracker.find_gray(gray[top:bottom, left:right], threshold)
            self.record("arrows.local", time.perf_counter() - local_start)
            if rect is not None:
                self.record("arrows.total", time.perf_counter() - start)
                return (rect[0] + left, rect[1] + top, rect[2], rect[3]), score
        full_start = time.perf_counter()
        rect, score = tracker.find_gray(gray, threshold)
        self.record("arrows.full", time.perf_counter() - full_start)
        self.record("arrows.total", time.perf_counter() - start)
        return rect, score
