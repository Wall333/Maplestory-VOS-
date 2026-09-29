"""Color-independent double-chevron shape detector for tracker.png."""

import cv2
import numpy as np


class ArrowShapeTracker:
    def __init__(self, path):
        image = cv2.imread(path, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Cannot load arrow tracker: {path}")
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        saturated = cv2.inRange(hsv, (0, 65, 75), (179, 255, 255))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(saturated)
        components = sorted(range(1, count), key=lambda label: stats[label, cv2.CC_STAT_AREA], reverse=True)
        if len(components) < 2:
            raise ValueError("tracker.png does not contain two separable arrows")
        arrows = np.isin(labels, components[:2]).astype(np.uint8) * 255
        dx = cv2.Sobel(arrows, cv2.CV_32F, 1, 0, ksize=3)
        dy = cv2.Sobel(arrows, cv2.CV_32F, 0, 1, ksize=3)
        magnitude_squared = dx * dx + dy * dy
        valid = magnitude_squared > 1
        self.cosine_kernel = np.divide(dx * dx - dy * dy, magnitude_squared,
                                       out=np.zeros_like(dx), where=valid)
        self.sine_kernel = np.divide(2 * dx * dy, magnitude_squared,
                                     out=np.zeros_like(dx), where=valid)
        self.edge_count = float(np.count_nonzero(valid))
        self.width = int(image.shape[1])
        self.height = int(image.shape[0])
        if self.edge_count < 20:
            raise ValueError("tracker.png arrow outline is too small")

    def find(self, frame, threshold):
        """Return a client-relative rectangle and polarity-independent shape score."""
        return self.find_gray(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), threshold)

    def find_gray(self, gray, threshold):
        """Match a preprocessed grayscale frame without converting it again."""
        if gray.shape[0] < self.height or gray.shape[1] < self.width:
            return None, 0.0
        dx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        dy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        magnitude_squared = dx * dx + dy * dy
        valid = magnitude_squared > 900
        cosine = np.divide(dx * dx - dy * dy, magnitude_squared,
                           out=np.zeros_like(dx), where=valid)
        sine = np.divide(2 * dx * dy, magnitude_squared,
                         out=np.zeros_like(dx), where=valid)
        response = (cv2.matchTemplate(cosine, self.cosine_kernel, cv2.TM_CCORR)
                    + cv2.matchTemplate(sine, self.sine_kernel, cv2.TM_CCORR)) / self.edge_count
        _, score, _, (x, y) = cv2.minMaxLoc(response)
        score = max(0.0, min(1.0, float(score)))
        if score < threshold:
            return None, score
        return (int(x), int(y), self.width, self.height), score
