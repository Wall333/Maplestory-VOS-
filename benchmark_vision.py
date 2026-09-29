"""Repeatable synthetic OpenCV threading benchmark (no game interaction)."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median
import time

import cv2
import numpy as np


NAMES = ("yeti", "yeti2", "crown", "crown2", "thorns", "area", "crystal")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if args.width < 100 or args.height < 100 or args.runs < 1:
        parser.error("width/height must be >= 100 and runs must be >= 1")
    frame = np.random.default_rng(7).integers(
        0, 256, (args.height, args.width, 3), dtype=np.uint8)
    assets = Path(__file__).resolve().parent / "assets"
    templates = [cv2.imread(str(assets / (name + ".png"))) for name in NAMES]
    if any(template is None for template in templates):
        parser.error("one or more benchmark templates are missing")

    def match(template):
        cv2.minMaxLoc(cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED))

    def serial():
        for template in templates:
            match(template)

    def parallel():
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(match, templates))

    def milliseconds(fn):
        fn()  # Warm-up is not included.
        samples = []
        for _ in range(args.runs):
            started = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - started) * 1000)
        return median(samples)

    original = cv2.getNumThreads()
    print(f"Synthetic {args.width}x{args.height}, OpenCV default threads={original}")
    try:
        for internal in (original, 1):
            cv2.setNumThreads(internal)
            print(f"internal={internal}: serial={milliseconds(serial):.1f} ms, "
                  f"3-worker pool={milliseconds(parallel):.1f} ms")
    finally:
        cv2.setNumThreads(original)


if __name__ == "__main__":
    main()
