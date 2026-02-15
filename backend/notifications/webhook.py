"""Generic webhook notification channel.

Sends a JSON POST to a configurable URL. Useful for integrating with
Home Assistant, IFTTT, n8n, or any custom service.

Setup:
1. Set WEBHOOK_URL in .env to your endpoint
"""

import logging

import requests

logger = logging.getLogger(__name__)


class WebhookNotifier:
    name = "webhook"

    def __init__(self, url):
        self.url = url

    def send(self, message, priority="normal", image_path=None):
        payload = {
            "message": message,
            "priority": priority,
            "source": "baby-sleep-tracker",
        }

        response = requests.post(
            self.url,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        logger.info("Webhook notification sent to %s", self.url)
