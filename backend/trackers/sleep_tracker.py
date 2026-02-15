"""Sleep tracker — higher-level sleep analytics on top of the detector.

Provides wake window tracking, daily stats, and sleep state machine.
"""

import logging
from datetime import datetime, time as dt_time, timedelta
from enum import Enum

from backend.config import BABY_AGE_MONTHS
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

    def __init__(self, baby_age_months=None):
        self.baby_age_months = baby_age_months if baby_age_months is not None else BABY_AGE_MONTHS
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

    def get_weekly_trends(self):
        """Get 7-day rolling stats: total sleep, nap count, longest nap per day."""
        today = datetime.now().date()
        results = []
        for days_ago in range(6, -1, -1):
            day = today - timedelta(days=days_ago)
            date_str = day.strftime("%Y-%m-%d")
            stats = self.get_daily_sleep_stats(date_str)
            stats["date"] = date_str
            stats["day_label"] = day.strftime("%a")
            results.append(stats)
        return results

    def get_night_sleep_stats(self, date_str=None):
        """Get sleep stats between 7pm–7am for a given night.

        If date_str is today or None, looks at last night (yesterday 7pm → today 7am).
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        night_start = datetime.combine(target_date - timedelta(days=1), dt_time(19, 0))
        night_end = datetime.combine(target_date, dt_time(7, 0))

        events = sqlite_store.get_sleep_events(limit=500)
        if not events:
            return {"total_minutes": 0, "wake_count": 0, "longest_stretch_minutes": 0}

        sleep_minutes = 0
        wake_count = 0
        longest_stretch = 0
        current_sleep_start = None

        for event in reversed(events):
            try:
                event_time = datetime.fromisoformat(event["start_time"])
            except (ValueError, TypeError):
                continue
            if event_time < night_start or event_time > night_end:
                continue

            if event["state"] == "asleep":
                current_sleep_start = event_time
            elif event["state"] == "awake":
                if current_sleep_start:
                    duration = (event_time - current_sleep_start).total_seconds() / 60
                    sleep_minutes += duration
                    longest_stretch = max(longest_stretch, duration)
                    current_sleep_start = None
                wake_count += 1

        # If still asleep at night_end, count up to night_end
        if current_sleep_start:
            duration = (night_end - current_sleep_start).total_seconds() / 60
            if duration > 0:
                sleep_minutes += duration
                longest_stretch = max(longest_stretch, duration)

        return {
            "total_minutes": round(sleep_minutes, 1),
            "wake_count": max(0, wake_count - 1),  # first "awake" isn't a night wake
            "longest_stretch_minutes": round(longest_stretch, 1),
        }

    def get_wake_window_status(self):
        """Get current wake window status with urgency level."""
        window_min, window_max = self.get_wake_window()
        awake_hours = self.get_time_awake_hours()
        awake_minutes = awake_hours * 60
        window_min_minutes = window_min * 60
        window_max_minutes = window_max * 60

        remaining_minutes = max(0, window_max_minutes - awake_minutes)

        if awake_minutes >= window_max_minutes:
            urgency = "red"
        elif awake_minutes >= window_min_minutes:
            urgency = "yellow"
        else:
            urgency = "green"

        return {
            "awake_minutes": round(awake_minutes, 1),
            "window_min_minutes": round(window_min_minutes, 1),
            "window_max_minutes": round(window_max_minutes, 1),
            "remaining_minutes": round(remaining_minutes, 1),
            "urgency": urgency,
            "baby_age_months": self.baby_age_months,
        }
