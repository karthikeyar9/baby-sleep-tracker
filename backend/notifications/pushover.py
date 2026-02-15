"""Pushover push notification channel.

Pushover is a $5 one-time purchase mobile app (iOS/Android) for receiving
push notifications. It supports priority levels, custom sounds, and image
attachments — ideal for baby monitor alerts.

Setup:
1. Create account at https://pushover.net
2. Register an application to get APP_TOKEN
3. Your user key is USER_KEY
4. Set PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY in .env
"""

import logging

import requests

logger = logging.getLogger(__name__)

PRIORITY_MAP = {
    "low": -1,
    "normal": 0,
    "high": 1,
    "urgent": 2,
}


class PushoverNotifier:
    name = "pushover"

    def __init__(self, app_token, user_key):
        self.app_token = app_token
        self.user_key = user_key

    def send(self, message, priority="normal", image_path=None):
        data = {
            "token": self.app_token,
            "user": self.user_key,
            "message": message,
            "priority": PRIORITY_MAP.get(priority, 0),
        }

        # Urgent priority requires retry/expire params
        if data["priority"] == 2:
            data["retry"] = 60
            data["expire"] = 300

        files = {}
        if image_path:
            try:
                files["attachment"] = ("snapshot.jpg", open(image_path, "rb"), "image/jpeg")
            except OSError:
                logger.warning("Could not attach image: %s", image_path)

        response = requests.post(
            "https://api.pushover.net/1/messages.json",
            data=data,
            files=files,
            timeout=10,
        )
        response.raise_for_status()
        logger.info("Pushover notification sent (priority=%s)", priority)
