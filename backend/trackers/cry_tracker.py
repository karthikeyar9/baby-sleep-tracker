"""Cry event tracker — stub for Phase 2 implementation.

Uses the CryDetector's output to track cry events with debouncing.
"""

import logging
import time

from backend.storage import sqlite_store

logger = logging.getLogger(__name__)


class CryTracker:
    """Tracks crying events with onset/offset debouncing.

    Requires multiple consecutive positive detections to trigger a cry event
    (onset_threshold), and multiple consecutive negatives to end it
    (offset_threshold). This prevents false positives from short noises.
    """

    def __init__(self, onset_threshold=3, offset_threshold=5):
        self.is_crying = False
        self.consecutive_cry = 0
        self.consecutive_quiet = 0
        self.cry_start_time = None
        self.onset_threshold = onset_threshold
        self.offset_threshold = offset_threshold

    def update(self, is_crying, confidence=0.0):
        """Update the tracker with a new detection result.

        Returns:
            tuple or None: ('cry_start', confidence) or ('cry_stop', duration_seconds)
        """
        event = None

        if is_crying:
            self.consecutive_cry += 1
            self.consecutive_quiet = 0
            if not self.is_crying and self.consecutive_cry >= self.onset_threshold:
                self.is_crying = True
                self.cry_start_time = time.time()
                event = ("cry_start", confidence)

                # Log to database
                from backend.detectors.cry_detector import CryDetector
                intensity = CryDetector().get_intensity(confidence)
                sqlite_store.log_cry_start(intensity)
                logger.info("Cry started (confidence: %.2f, intensity: %s)", confidence, intensity)
        else:
            self.consecutive_quiet += 1
            self.consecutive_cry = 0
            if self.is_crying and self.consecutive_quiet >= self.offset_threshold:
                self.is_crying = False
                duration = time.time() - self.cry_start_time
                event = ("cry_stop", duration)

                sqlite_store.log_cry_end(int(duration))
                logger.info("Cry stopped after %.0f seconds", duration)

        return event
