"""Sleep tracker — higher-level sleep analytics on top of the detector.

Provides wake window tracking, daily stats, and sleep state machine.
"""

import logging
from datetime import datetime, time as dt_time, timedelta
from enum import Enum

from backend.storage import sqlite_store

logger = logging.getLogger(__name__)


class SleepState(Enum):
    AWAKE = "awake"
    DROWSY = "drowsy"
    LIGHT_SLEEP = "light"
    DEEP_SLEEP = "deep"
    CRYING = "crying"


# Wake windows by age in months: (min_hours, max_hours)
WAKE_WINDOWS = {
    0: (0.5, 1.0),
    3: (1.25, 1.75),
    6: (2.0, 3.0),
    9: (2.5, 3.5),
    12: (3.0, 4.0),
    18: (4.0, 6.0),
    24: (5.0, 6.0),
}


class SleepTracker:
    """Tracks sleep patterns and provides analytics."""

    def __init__(self, baby_age_months=6):
        self.baby_age_months = baby_age_months
        self.current_state = SleepState.AWAKE
        self.state_start_time = datetime.now()

    def get_wake_window(self):
        """Get the recommended wake window for the baby's age."""
        best_match = 0
        for age in sorted(WAKE_WINDOWS.keys()):
            if age <= self.baby_age_months:
                best_match = age
        return WAKE_WINDOWS.get(best_match, (2.0, 3.0))

    def get_time_awake_hours(self):
        """Get how long the baby has been awake (if currently awake)."""
        if self.current_state == SleepState.AWAKE:
            delta = datetime.now() - self.state_start_time
            return delta.total_seconds() / 3600
        return 0.0

    def get_daily_sleep_stats(self, date_str=None):
        """Get sleep statistics for a given day."""
        events = sqlite_store.get_sleep_events(limit=200)
        if not events:
            return {"total_nap_minutes": 0, "nap_count": 0, "longest_nap_minutes": 0}

        # Filter to the target date
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        nap_minutes = 0
        nap_count = 0
        longest_nap = 0
        current_nap_start = None

        for event in reversed(events):
            event_date = event["start_time"][:10]
            if event_date != date_str:
                continue

            if event["state"] == "asleep":
                current_nap_start = event["start_time"]
                nap_count += 1
            elif event["state"] == "awake" and current_nap_start:
                try:
                    start = datetime.fromisoformat(current_nap_start)
                    end = datetime.fromisoformat(event["start_time"])
                    duration = (end - start).total_seconds() / 60
                    nap_minutes += duration
                    longest_nap = max(longest_nap, duration)
                except (ValueError, TypeError):
                    pass
                current_nap_start = None

        return {
            "total_nap_minutes": round(nap_minutes, 1),
            "nap_count": nap_count,
            "longest_nap_minutes": round(longest_nap, 1),
        }
