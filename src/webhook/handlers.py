"""
Alert handler.
Routes parsed alerts to the appropriate exchange client and trade executor.
"""

import logging
from typing import Any

from src.config import Settings
from src.exchanges.base import BaseExchange
from src.storage.database import Database
from src.trading.executor import TradeExecutor
from src.trading.risk_manager import RiskManager
from src.notifications.telegram import TelegramNotifier
from src.notifications.discord import DiscordNotifier
from src.webhook.parser import AlertData

logger = logging.getLogger("webhook.handler")


class AlertHandler:
    """
    Central handler that coordinates alert processing:
    1. Resolves the target exchange client
    2. Checks risk management constraints
    3. Executes the trade
    4. Logs the trade
    5. Sends notifications
    """

    def __init__(
        self,
        exchange_clients: dict[str, BaseExchange],
        settings: Settings,
        database: Database,
    ) -> None:
        self._clients = exchange_clients
        self._settings = settings
        self._db = database
        self._risk_manager = RiskManager(settings.risk, database)
        self._executor = TradeExecutor(settings)
        self._telegram = TelegramNotifier(settings.notifications)
        self._discord = DiscordNotifier(settings.notifications)

    def _resolve_client(self, alert: AlertData) -> BaseExchange:
        """Find the exchange client for the alert's account/exchange."""
        # Try exact account name first
        if alert.account and alert.account in self._clients:
            return self._clients[alert.account]

        # Fall back to first client matching the exchange
        for name, client in self._clients.items():
            if client.EXCHANGE_NAME == alert.exchange:
                return client

        raise ValueError(
            f"No exchange client found for account='{alert.account}', "
            f"exchange='{alert.exchange}'"
        )

    async def handle(self, alert: AlertData) -> dict[str, Any]:
        """
        Process an incoming alert through the full pipeline.
        Returns a result dict with trade details.
        """
        client = self._resolve_client(alert)
        result: dict[str, Any] = {}

        # --- Risk checks for opening actions ---
        if alert.action.startswith("open_") or alert.action in ("scale_in", "reverse"):
            risk_check = await self._risk_manager.check(alert, client)
            if not risk_check["allowed"]:
                reason = risk_check["reason"]
                logger.warning("Trade blocked by risk manager: %s", reason)
                await self._notify_risk_block(alert, reason)
                return {"status": "blocked", "reason": reason}

        try:
            result = await self._executor.execute(alert, client)
        except Exception as e:
            logger.exception("Trade execution failed: %s", e)
            await self._notify_error(alert, str(e))
            raise

        # --- Log trade ---
        try:
            await self._db.log_trade(
                exchange=alert.exchange,
                symbol=alert.symbol,
                action=alert.action,
                side=result.get("side", ""),
                quantity=result.get("quantity", 0),
                price=result.get("price", 0),
                order_type=alert.order_type,
                stop_loss=alert.stop_loss,
                take_profit=alert.take_profit,
                leverage=alert.leverage,
                account=alert.account,
                order_id=result.get("order_id", ""),
                comment=alert.comment,
            )
        except Exception as e:
            logger.error("Failed to log trade: %s", e)

        # --- Notifications ---
        await self._notify_trade(alert, result)

        return result

    async def _notify_trade(self, alert: AlertData, result: dict) -> None:
        """Send trade notifications."""
        is_open = alert.action.startswith("open_") or alert.action in ("scale_in", "reverse")
        is_close = alert.action.startswith("close_") or alert.action == "scale_out"
        notif_cfg = self._settings.notifications

        should_notify = (
            (is_open and notif_cfg.get("notify_on_open", True))
            or (is_close and notif_cfg.get("notify_on_close", True))
            or alert.action in ("set_sl", "set_tp", "cancel_orders")
        )

        if not should_notify:
            return

        message = self._format_trade_message(alert, result)
        await self._send_notifications(message)

    async def _notify_error(self, alert: AlertData, error: str) -> None:
        """Send error notifications."""
        if not self._settings.notifications.get("notify_on_error", True):
            return

        message = (
            f"TRADE ERROR\n"
            f"Exchange: {alert.exchange.capitalize()}\n"
            f"Symbol: {alert.symbol}\n"
            f"Action: {alert.action}\n"
            f"Error: {error}"
        )
        await self._send_notifications(message)

    async def _notify_risk_block(self, alert: AlertData, reason: str) -> None:
        """Send risk limit notifications."""
        if not self._settings.notifications.get("notify_on_risk_limit", True):
            return

        message = (
            f"TRADE BLOCKED\n"
            f"Exchange: {alert.exchange.capitalize()}\n"
            f"Symbol: {alert.symbol}\n"
            f"Action: {alert.action}\n"
            f"Reason: {reason}"
        )
        await self._send_notifications(message)

    async def _send_notifications(self, message: str) -> None:
        """Send message to all enabled notification channels."""
        if self._settings.notifications.get("telegram_enabled"):
            await self._telegram.send(message)
        if self._settings.notifications.get("discord_enabled"):
            await self._discord.send(message)

    def _format_trade_message(self, alert: AlertData, result: dict) -> str:
        """Format a human-readable trade notification message."""
        action_label = alert.action.upper().replace("_", " ")
        lines = [
            f"TRADE {action_label}",
            f"Exchange: {alert.exchange.capitalize()}",
            f"Symbol: {alert.symbol}",
        ]

        if result.get("side"):
            lines.append(f"Side: {result['side'].upper()}")
        if result.get("quantity"):
            qty = result["quantity"]
            price = result.get("price", 0)
            notional = qty * price if price else 0
            lines.append(f"Size: {qty} (${notional:,.2f})")
        if result.get("price"):
            lines.append(f"Price: ${result['price']:,.2f}")
        if alert.stop_loss:
            lines.append(f"Stop Loss: ${alert.stop_loss:,.2f}")
        if alert.take_profit:
            lines.append(f"Take Profit: ${alert.take_profit:,.2f}")
        if alert.leverage:
            lines.append(f"Leverage: {alert.leverage}x")
        if alert.account:
            lines.append(f"Account: {alert.account}")

        return "\n".join(lines)
