"""
Telegram notification sender.
Sends trade alerts, errors, and risk warnings to a Telegram chat
via the Bot API.
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("notifications.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramNotifier:
    """Sends notifications to Telegram using the Bot API."""

    def __init__(self, notif_config: dict) -> None:
        self._enabled = notif_config.get("telegram_enabled", False)
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self._parse_mode = "HTML"
        self._http: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self._enabled and self._token and self._chat_id)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._http

    async def send(self, message: str) -> bool:
        """
        Send a text message to the configured Telegram chat.

        Args:
            message: The message text to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.configured:
            logger.debug("Telegram not configured, skipping notification")
            return False

        url = f"{TELEGRAM_API_BASE}/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": self._format_message(message),
            "parse_mode": self._parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            client = await self._get_client()
            response = await client.post(url, json=payload)
            data = response.json()

            if data.get("ok"):
                logger.debug("Telegram message sent successfully")
                return True
            else:
                logger.error(
                    "Telegram API error: %s",
                    data.get("description", "Unknown error"),
                )
                return False

        except httpx.RequestError as e:
            logger.error("Telegram request failed: %s", e)
            return False
        except Exception as e:
            logger.error("Telegram notification error: %s", e)
            return False

    async def send_with_image(self, message: str, image_url: str) -> bool:
        """Send a message with an image (e.g., chart screenshot)."""
        if not self.configured:
            return False

        url = f"{TELEGRAM_API_BASE}/bot{self._token}/sendPhoto"
        payload = {
            "chat_id": self._chat_id,
            "photo": image_url,
            "caption": self._format_message(message),
            "parse_mode": self._parse_mode,
        }

        try:
            client = await self._get_client()
            response = await client.post(url, json=payload)
            return response.json().get("ok", False)
        except Exception as e:
            logger.error("Telegram photo send failed: %s", e)
            return False

    def _format_message(self, text: str) -> str:
        """Format the message with a bot header and HTML escaping."""
        # Escape HTML special characters in the message body
        safe_text = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        lines = safe_text.split("\n")
        if lines:
            # Bold the first line (title)
            lines[0] = f"<b>{lines[0]}</b>"

        header = "📊 <b>TradingView Webhook Bot</b>\n" + "─" * 28 + "\n"
        return header + "\n".join(lines)

    async def test_connection(self) -> dict[str, Any]:
        """
        Test the Telegram bot connection.
        Returns bot info if successful.
        """
        if not self._token:
            return {"ok": False, "error": "No bot token configured"}

        url = f"{TELEGRAM_API_BASE}/bot{self._token}/getMe"

        try:
            client = await self._get_client()
            response = await client.get(url)
            data = response.json()

            if data.get("ok"):
                bot = data["result"]
                return {
                    "ok": True,
                    "bot_name": bot.get("first_name", ""),
                    "bot_username": bot.get("username", ""),
                }
            return {"ok": False, "error": data.get("description", "Unknown")}

        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()
