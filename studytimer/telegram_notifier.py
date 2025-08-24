from __future__ import annotations
import os
from typing import Optional

try:
    from telegram import Bot
except Exception:  # pragma: no cover - telegram might be missing in env
    Bot = None  # type: ignore

class TelegramNotifier:
    """Send messages via Telegram bot if configured."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.bot = Bot(self.token) if self.token and self.chat_id and Bot else None

    def send_message(self, text: str) -> None:
        if not self.bot:
            # Fallback to console output when Telegram isn't configured
            print(f"Telegram disabled: {text}")
            return
        try:
            self.bot.send_message(chat_id=self.chat_id, text=text)
        except Exception as exc:  # pragma: no cover
            print(f"Error sending Telegram message: {exc}")
