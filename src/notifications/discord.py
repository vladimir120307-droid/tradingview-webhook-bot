"""
Discord notification sender.
Sends trade alerts to a Discord channel via webhook URL.
"""

import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("notifications.discord")

# Discord embed color codes
COLOR_SUCCESS = 0x00FF00    # Green
COLOR_ERROR = 0xFF0000      # Red
COLOR_WARNING = 0xFFA500    # Orange
COLOR_INFO = 0x3498DB       # Blue


class DiscordNotifier:
    """Sends notifications to Discord using webhooks."""

    def __init__(self, notif_config: dict) -> None:
        self._enabled = notif_config.get("discord_enabled", False)
        self._webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
        self._username = "TradingView Bot"
        self._http: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self._enabled and self._webhook_url)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._http

    async def send(self, message: str) -> bool:
        """
        Send a message to Discord via webhook.

        Args:
            message: The notification message text.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.configured:
            logger.debug("Discord not configured, skipping notification")
            return False

        # Determine embed color based on message content
        color = self._detect_color(message)

        lines = message.strip().split("\n")
        title = lines[0] if lines else "Trade Notification"
        description = "\n".join(lines[1:]) if len(lines) > 1 else ""

        payload = {
            "username": self._username,
            "embeds": [
                {
                    "title": title,
                    "description": f"```\n{description}\n```" if description else "",
                    "color": color,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "footer": {
                        "text": "TradingView Webhook Bot",
                    },
                }
            ],
        }

        try:
            client = await self._get_client()
            response = await client.post(self._webhook_url, json=payload)

            if response.status_code in (200, 204):
                logger.debug("Discord message sent successfully")
                return True
            else:
                logger.error(
                    "Discord webhook error: %s %s",
                    response.status_code, response.text,
                )
                return False

        except httpx.RequestError as e:
            logger.error("Discord request failed: %s", e)
            return False
        except Exception as e:
            logger.error("Discord notification error: %s", e)
            return False

    async def send_plain(self, message: str) -> bool:
        """Send a plain text message (no embed) to Discord."""
        if not self.configured:
            return False

        payload = {
            "username": self._username,
            "content": message[:2000],  # Discord's message limit
        }

        try:
            client = await self._get_client()
            response = await client.post(self._webhook_url, json=payload)
            return response.status_code in (200, 204)
        except Exception as e:
            logger.error("Discord plain message failed: %s", e)
            return False

    @staticmethod
    def _detect_color(message: str) -> int:
        """Detect the appropriate embed color based on message keywords."""
        upper = message.upper()
        if "ERROR" in upper or "FAILED" in upper:
            return COLOR_ERROR
        if "BLOCKED" in upper or "WARNING" in upper or "LIMIT" in upper:
            return COLOR_WARNING
        if "OPENED" in upper or "OPEN" in upper:
            return COLOR_SUCCESS
        if "CLOSED" in upper or "CLOSE" in upper:
            return COLOR_INFO
        return COLOR_INFO

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()
