"""Diaper change tracker — manual entry with smart reminders."""

import logging
import time

from backend.storage import sqlite_store
from backend.config import NOTIFICATION_COOLDOWN_SECONDS

logger = logging.getLogger(__name__)

# Default: remind after 4 hours with no logged change
DIAPER_REMINDER_HOURS = 4


class DiaperTracker:
    """Tracks diaper changes and provides reminders."""

    def __init__(self, reminder_hours=DIAPER_REMINDER_HOURS):
        self.reminder_hours = reminder_hours
        self.last_reminder_time = 0

    def log_change(self, diaper_type, notes=""):
        """Log a diaper change.

        Args:
            diaper_type: One of 'wet', 'dirty', 'both', 'dry'
            notes: Optional notes
        """
        sqlite_store.log_diaper_event(diaper_type, notes)
        logger.info("Diaper change logged: %s", diaper_type)

    def get_stats(self, date_str=None):
        """Get diaper statistics for a given day."""
        return sqlite_store.get_diaper_stats(date_str)

    def get_history(self, limit=50):
        """Get recent diaper events."""
        return sqlite_store.get_diaper_events(limit=limit)

    def check_reminder_needed(self):
        """Check if a diaper change reminder should be sent.

        Returns:
            tuple or None: ('diaper_reminder', hours_since_last) if reminder needed
        """
        stats = sqlite_store.get_diaper_stats()
        last = stats.get("last_change")
        if last is None:
            return None

        from datetime import datetime
        try:
            last_time = datetime.fromisoformat(last["timestamp"])
            hours_since = (datetime.now() - last_time).total_seconds() / 3600
        except (ValueError, TypeError, KeyError):
            return None

        now = time.time()
        if hours_since >= self.reminder_hours and (now - self.last_reminder_time) > NOTIFICATION_COOLDOWN_SECONDS:
            self.last_reminder_time = now
            return ("diaper_reminder", round(hours_since, 1))

        return None
