"""Notification dispatcher — routes events to configured notification channels."""

import logging
import time

from backend.config import (
    NOTIFICATION_COOLDOWN_SECONDS,
    PUSHOVER_APP_TOKEN,
    PUSHOVER_USER_KEY,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_BOT_CHAT_ID,
    WEBHOOK_URL,
)
from backend.storage import sqlite_store

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Dispatches notifications to all configured channels with cooldown."""

    def __init__(self):
        self.channels = []
        self.cooldowns = {}  # event_type -> last_sent_timestamp
        self.cooldown_seconds = NOTIFICATION_COOLDOWN_SECONDS

        if PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY:
            from backend.notifications.pushover import PushoverNotifier
            self.channels.append(PushoverNotifier(PUSHOVER_APP_TOKEN, PUSHOVER_USER_KEY))
            logger.info("Pushover notifications enabled")

        if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_CHAT_ID:
            from backend.notifications.telegram import TelegramNotifier
            self.channels.append(TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_CHAT_ID))
            logger.info("Telegram notifications enabled")

        if WEBHOOK_URL:
            from backend.notifications.webhook import WebhookNotifier
            self.channels.append(WebhookNotifier(WEBHOOK_URL))
            logger.info("Webhook notifications enabled")

        if not self.channels:
            logger.info("No notification channels configured")

    def notify(self, event_type, message, priority="normal", image_path=None):
        """Send a notification to all channels, respecting cooldowns.

        Args:
            event_type: e.g. 'baby_crying', 'baby_woke_up', 'diaper_reminder'
            message: Human-readable notification text
            priority: 'low', 'normal', 'high', 'urgent'
            image_path: Optional path to an image to attach

        Returns:
            bool: True if notification was sent, False if cooled down
        """
        now = time.time()
        if event_type in self.cooldowns:
            elapsed = now - self.cooldowns[event_type]
            if elapsed < self.cooldown_seconds:
                logger.debug("Notification cooldown for %s (%.0fs remaining)",
                             event_type, self.cooldown_seconds - elapsed)
                return False

        self.cooldowns[event_type] = now
        sent = False

        for channel in self.channels:
            try:
                channel.send(message, priority=priority, image_path=image_path)
                sqlite_store.log_notification(event_type, channel.name, message, delivered=True)
                sent = True
            except Exception as e:
                logger.error("Failed to send via %s: %s", channel.name, e)
                sqlite_store.log_notification(event_type, channel.name, message, delivered=False)

        if sent:
            logger.info("Notification sent [%s]: %s", event_type, message)

        return sent
