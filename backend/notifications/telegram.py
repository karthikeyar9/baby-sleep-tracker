"""Telegram bot notification channel.

Setup:
1. Create a bot via @BotFather on Telegram
2. Get the bot token
3. Get your chat ID (message the bot, then check /getUpdates)
4. Set TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_CHAT_ID in .env
"""

import logging

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    name = "telegram"

    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def send(self, message, priority="normal", image_path=None):
        if image_path:
            self._send_photo(message, image_path)
        else:
            self._send_message(message)

    def _send_message(self, text):
        response = requests.get(
            f"{self.base_url}/sendMessage",
            params={"chat_id": self.chat_id, "text": text},
            timeout=10,
        )
        response.raise_for_status()
        logger.info("Telegram message sent")

    def _send_photo(self, caption, image_path):
        try:
            with open(image_path, "rb") as photo:
                response = requests.post(
                    f"{self.base_url}/sendPhoto",
                    data={"chat_id": self.chat_id, "caption": caption},
                    files={"photo": photo},
                    timeout=15,
                )
                response.raise_for_status()
                logger.info("Telegram photo sent")
        except OSError:
            logger.warning("Could not open image %s, sending text only", image_path)
            self._send_message(caption)
