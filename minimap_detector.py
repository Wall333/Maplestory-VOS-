"""Locate the movable minimap and count coloured character markers on shared frames."""

import threading
import time

import cv2
import numpy as np


def static_map_mask(template):
    """Match distinctive map artwork, excluding the two movable markers."""
    height, width = template.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[round(height * .20):round(height * .86),
         round(width * .27):round(width * .73)] = 255
    hsv = cv2.cvtColor(template, cv2.COLOR_BGR2HSV)
    red = cv2.bitwise_or(cv2.inRange(hsv, (0, 90, 90), (10, 255, 255)),
                         cv2.inRange(hsv, (170, 90, 90), (179, 255, 255)))
    yellow = cv2.inRange(hsv, (18, 90, 90), (40, 255, 255))
    moving = cv2.dilate(cv2.bitwise_or(red, yellow),
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    mask[moving != 0] = 0
    return mask


def locate_minimap(gray, template, mask, cache=None, padding=120, threshold=.90,
                   timing=None, color=None):
    if gray is None or template is None:
        return None, 0.0
    height, width = template.shape[:2]
    if gray.shape[0] < height or gray.shape[1] < width:
        return None, 0.0

    def search(region, left, top, stage):
        started = time.perf_counter()
        result = cv2.matchTemplate(region, template, cv2.TM_SQDIFF_NORMED, mask=mask)
        best_score = 0.0
        best_rect = None
        for _ in range(8):
            minimum, _, position, _ = cv2.minMaxLoc(result)
            score = max(0.0, 1.0 - float(minimum))
            best_score = max(best_score, score)
            if score < threshold:
                break
            candidate = (left + position[0], top + position[1], width, height)
            if color is None or marker_boxes(color, candidate)[1] is not None:
                best_rect, best_score = candidate, score
                break
            # Try the next distinct location instead of trusting a generic UI patch.
            px, py = position
            cv2.rectangle(result, (max(0, px - width // 2), max(0, py - height // 2)),
                          (min(result.shape[1] - 1, px + width // 2),
                           min(result.shape[0] - 1, py + height // 2)), 1.0, -1)
        if timing is not None:
            timing(stage, time.perf_counter() - started)
        return best_rect, best_score

    if cache is not None:
        x, y, _, _ = cache
        left, top = max(0, x - padding), max(0, y - padding)
        right = min(gray.shape[1], x + width + padding)
        bottom = min(gray.shape[0], y + height + padding)
        if right - left >= width and bottom - top >= height:
            rect, score = search(gray[top:bottom, left:right], left, top, "minimap.local")
            if rect is not None:
                return rect, score
    rect, score = search(gray, 0, 0, "minimap.full")
    return rect, score


def marker_boxes(color, minimap_rect):
    """Return client-relative red marker boxes and the largest yellow marker box."""
    x, y, width, height = minimap_rect
    inset_left, inset_right = round(width * .26), round(width * .74)
    inset_top, inset_bottom = round(height * .23), round(height * .88)
    crop = color[y + inset_top:y + inset_bottom, x + inset_left:x + inset_right]
    if crop.size == 0:
        return (), None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    red = cv2.bitwise_or(cv2.inRange(hsv, (0, 110, 110), (10, 255, 255)),
                         cv2.inRange(hsv, (170, 110, 110), (179, 255, 255)))
    yellow = cv2.inRange(hsv, (18, 110, 110), (40, 255, 255))

    def components(mask, min_area):
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        boxes = []
        for index in range(1, count):
            bx, by, bw, bh, area = map(int, stats[index])
            if min_area <= area <= 100 and 3 <= bw <= 14 and 3 <= bh <= 14:
                boxes.append(((x + inset_left + bx, y + inset_top + by, bw, bh), area))
        return boxes

    reds = tuple(box for box, _ in components(red, 8))
    yellows = components(yellow, 12)
    player = max(yellows, key=lambda item: item[1])[0] if yellows else None
    return reds, player


class MinimapDetector:
    def __init__(self, app, log_fn):
        self.app = app
        self.log_fn = log_fn
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="minimap-detector", daemon=True)
        self.template = app.vision.gray_templates.get("minimap")
        color_template = app.vision.templates.get("minimap")
        self.mask = static_map_mask(color_template) if color_template is not None else None
        self.context = None
        self.rect = None
        self.score = 0.0
        self.reds = ()
        self.player = None
        self.count = 0
        self.pending_count = None
        self.pending_streak = 0
        self.checked_at = 0.0

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def snapshot(self):
        with self.lock:
            return self.rect, self.score, self.reds, self.player, self.count, self.checked_at

    def _run(self):
        sequence = 0
        last_check = 0.0
        while not self.stop_event.is_set():
            frame = self.app.vision.wait_next(sequence, .25)
            if frame is None:
                continue
            sequence = frame.sequence
            config = self.app.config
            enabled = bool(config.get("minimap_checker_enabled", False))
            if frame.context != self.context or not enabled:
                with self.lock:
                    self.context = frame.context
                    self.rect = None
                    self.reds = ()
                    self.player = None
                    self.count = 0
                    self.pending_count = None
                    self.pending_streak = 0
                    self.checked_at = 0.0
            if not enabled or frame.gray is None or frame.color is None or self.template is None:
                continue
            now = time.monotonic()
            rate = max(1.0, float(config.get("minimap_checks_per_second", 5)))
            if now - last_check < 1 / rate:
                continue
            last_check = now
            started = time.perf_counter()
            with self.lock:
                cache = self.rect
            rect, score = locate_minimap(
                frame.gray, self.template, self.mask, cache,
                int(config.get("vision_roi_padding", 120)),
                float(config.get("minimap_match_threshold", .90)),
                self.app.vision.record, frame.color)
            reds, player = marker_boxes(frame.color, rect) if rect is not None else ((), None)
            with self.lock:
                self.rect, self.score = rect, score
                self.reds, self.player = reds, player
                self.checked_at = time.monotonic()
                observed = len(reds) if rect is not None else 0
                if observed == self.pending_count:
                    self.pending_streak += 1
                else:
                    self.pending_count, self.pending_streak = observed, 1
                if self.pending_streak >= 2 and observed != self.count:
                    self.count = observed
                    self.log_fn(f"Minimap: {observed} other player marker(s)")
            self.app.vision.record("cycle.minimap", time.perf_counter() - started)
