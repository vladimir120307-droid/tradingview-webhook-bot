"""
Risk manager.
Enforces trading limits: daily loss cap, max positions, leverage caps,
and minimum order values before any trade is placed.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from src.exchanges.base import BaseExchange
from src.storage.database import Database
from src.webhook.parser import AlertData

logger = logging.getLogger("trading.risk")


class RiskManager:
    """
    Validates incoming trades against risk management rules.
    Blocks trades that would violate configured risk parameters.
    """

    def __init__(self, risk_config: dict, database: Database) -> None:
        self._config = risk_config
        self._db = database
        self._daily_loss: float = 0.0
        self._daily_reset_date: str = ""

    async def check(self, alert: AlertData, client: BaseExchange) -> dict[str, Any]:
        """
        Run all risk checks for an incoming alert.
        Returns {"allowed": True/False, "reason": str}.
        """
        # Check daily loss limit
        daily_check = await self._check_daily_loss(client)
        if not daily_check["allowed"]:
            return daily_check

        # Check max positions
        pos_check = await self._check_max_positions(alert, client)
        if not pos_check["allowed"]:
            return pos_check

        # Check leverage cap
        lev_check = self._check_leverage(alert)
        if not lev_check["allowed"]:
            return lev_check

        # Check max single trade size
        size_check = await self._check_trade_size(alert, client)
        if not size_check["allowed"]:
            return size_check

        return {"allowed": True, "reason": ""}

    async def _check_daily_loss(self, client: BaseExchange) -> dict[str, Any]:
        """Check if the daily loss limit has been reached."""
        limit_pct = self._config.get("daily_loss_limit_percent", 0)
        if limit_pct <= 0:
            return {"allowed": True, "reason": ""}

        reset_hour = self._config.get("daily_loss_reset_hour", 0)
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        # Reset daily counter at the configured hour
        if today != self._daily_reset_date or now.hour >= reset_hour:
            if today != self._daily_reset_date:
                self._daily_loss = 0.0
                self._daily_reset_date = today

        # Calculate today's realized P&L from the database
        daily_pnl = await self._db.get_daily_pnl(today)
        balance = await client.get_balance()

        if balance.total <= 0:
            return {"allowed": True, "reason": ""}

        loss_pct = abs(min(daily_pnl, 0)) / balance.total * 100

        if loss_pct >= limit_pct:
            reason = (
                f"Daily loss limit reached: {loss_pct:.2f}% "
                f"(limit: {limit_pct:.1f}%)"
            )
            logger.warning(reason)
            return {"allowed": False, "reason": reason}

        return {"allowed": True, "reason": ""}

    async def _check_max_positions(
        self, alert: AlertData, client: BaseExchange
    ) -> dict[str, Any]:
        """Check if opening a new position would exceed max position limits."""
        max_positions = self._config.get("max_positions", 0)
        max_per_symbol = self._config.get("max_positions_per_symbol", 0)

        if max_positions <= 0 and max_per_symbol <= 0:
            return {"allowed": True, "reason": ""}

        # Count current open positions from the database
        open_positions = await self._db.count_open_positions()
        symbol_positions = await self._db.count_symbol_positions(alert.symbol)

        if max_positions > 0 and open_positions >= max_positions:
            reason = (
                f"Max positions reached: {open_positions}/{max_positions}"
            )
            logger.warning(reason)
            return {"allowed": False, "reason": reason}

        if max_per_symbol > 0 and symbol_positions >= max_per_symbol:
            reason = (
                f"Max positions for {alert.symbol} reached: "
                f"{symbol_positions}/{max_per_symbol}"
            )
            logger.warning(reason)
            return {"allowed": False, "reason": reason}

        return {"allowed": True, "reason": ""}

    def _check_leverage(self, alert: AlertData) -> dict[str, Any]:
        """Check if the requested leverage exceeds the configured maximum."""
        max_leverage = self._config.get("max_leverage", 125)
        requested = alert.leverage or self._config.get("default_leverage", 1)

        if requested > max_leverage:
            reason = (
                f"Leverage {requested}x exceeds max allowed {max_leverage}x"
            )
            logger.warning(reason)
            return {"allowed": False, "reason": reason}

        return {"allowed": True, "reason": ""}

    async def _check_trade_size(
        self, alert: AlertData, client: BaseExchange
    ) -> dict[str, Any]:
        """Check if the trade size is within acceptable bounds."""
        min_value = self._config.get("min_order_value", 10.0)
        max_pct = self._config.get("max_single_trade_percent", 100.0)

        balance = await client.get_balance()

        # Check max percentage
        if alert.size_type == "percent" and alert.size_value > max_pct:
            reason = (
                f"Trade size {alert.size_value}% exceeds max "
                f"allowed {max_pct}%"
            )
            logger.warning(reason)
            return {"allowed": False, "reason": reason}

        # Check minimum order value for fixed size
        if alert.size_type == "fixed" and alert.size_value < min_value:
            reason = (
                f"Order value ${alert.size_value:.2f} below minimum "
                f"${min_value:.2f}"
            )
            logger.warning(reason)
            return {"allowed": False, "reason": reason}

        # Check if the trade would exceed available balance
        if alert.size_type == "percent":
            trade_value = balance.available * (alert.size_value / 100)
        elif alert.size_type == "fixed":
            trade_value = alert.size_value
        else:
            trade_value = balance.available * 0.1  # Conservative estimate

        if trade_value > balance.available:
            reason = (
                f"Insufficient balance: trade=${trade_value:,.2f}, "
                f"available=${balance.available:,.2f}"
            )
            logger.warning(reason)
            return {"allowed": False, "reason": reason}

        return {"allowed": True, "reason": ""}

    async def update_daily_loss(self, pnl: float) -> None:
        """Update the daily loss counter after a trade closes."""
        if pnl < 0:
            self._daily_loss += abs(pnl)
            logger.info("Daily loss updated: $%.2f", self._daily_loss)
