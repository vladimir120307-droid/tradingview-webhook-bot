"""
Trade executor.
Translates alert actions into exchange API calls, handling order placement,
position management, SL/TP, and order lifecycle.
"""

import logging
from typing import Any

from src.config import Settings
from src.exchanges.base import BaseExchange, OrderResult
from src.trading.position_sizer import PositionSizer
from src.trading.order_manager import OrderManager
from src.webhook.parser import AlertData

logger = logging.getLogger("trading.executor")


class TradeExecutor:
    """Executes trades based on parsed alert data."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sizer = PositionSizer(settings.risk)
        self._order_mgr = OrderManager(settings.trading)

    async def execute(self, alert: AlertData, client: BaseExchange) -> dict[str, Any]:
        """
        Execute a trade action on the given exchange client.
        Returns a dict with execution results.
        """
        action = alert.action
        dispatch = {
            "open_long": self._open_position,
            "open_short": self._open_position,
            "close_long": self._close_position,
            "close_short": self._close_position,
            "close_all": self._close_all,
            "cancel_orders": self._cancel_orders,
            "set_sl": self._set_stop_loss,
            "set_tp": self._set_take_profit,
            "reverse": self._reverse_position,
            "scale_in": self._scale_in,
            "scale_out": self._scale_out,
        }

        handler = dispatch.get(action)
        if handler is None:
            raise ValueError(f"Unknown action: {action}")

        return await handler(alert, client)

    async def _open_position(self, alert: AlertData, client: BaseExchange) -> dict[str, Any]:
        """Open a new long or short position."""
        is_long = alert.action == "open_long"
        side = "BUY" if is_long else "SELL"

        # Calculate position size
        balance = await client.get_balance()
        current_price = await client.get_ticker_price(alert.symbol)

        quantity = self._sizer.calculate(
            balance=balance.available,
            current_price=current_price,
            size_type=alert.size_type,
            size_value=alert.size_value,
            stop_loss=alert.stop_loss,
            leverage=alert.leverage or self._settings.risk.get("default_leverage", 1),
        )

        leverage = alert.leverage or self._settings.risk.get("default_leverage", 1)

        # Place the order
        order = await self._order_mgr.place_order(
            client=client,
            symbol=alert.symbol,
            side=side,
            quantity=quantity,
            order_type=alert.order_type,
            price=alert.price,
            leverage=leverage,
        )

        result = self._order_to_dict(order, side="long" if is_long else "short")

        # Set SL/TP if provided
        position_side = "long" if is_long else "short"
        if alert.stop_loss:
            try:
                await client.set_stop_loss(alert.symbol, position_side, alert.stop_loss)
                result["stop_loss"] = alert.stop_loss
            except Exception as e:
                logger.error("Failed to set SL: %s", e)

        if alert.take_profit:
            try:
                await client.set_take_profit(alert.symbol, position_side, alert.take_profit)
                result["take_profit"] = alert.take_profit
            except Exception as e:
                logger.error("Failed to set TP: %s", e)

        logger.info(
            "Position opened: %s %s %s qty=%s price=%s lev=%dx",
            alert.exchange, side, alert.symbol, quantity,
            result.get("price", "market"), leverage,
        )

        return result

    async def _close_position(self, alert: AlertData, client: BaseExchange) -> dict[str, Any]:
        """Close an existing position."""
        side = "long" if alert.action == "close_long" else "short"

        # Cancel existing SL/TP orders first
        await client.cancel_all_orders(alert.symbol)

        order = await client.close_position(alert.symbol, side)
        if order is None:
            return {"status": "no_position", "symbol": alert.symbol, "side": side}

        logger.info("Position closed: %s %s %s", alert.exchange, side, alert.symbol)
        return self._order_to_dict(order, side=side)

    async def _close_all(self, alert: AlertData, client: BaseExchange) -> dict[str, Any]:
        """Close all positions and cancel all orders for a symbol."""
        await client.cancel_all_orders(alert.symbol)
        order = await client.close_position(alert.symbol)
        if order is None:
            return {"status": "no_position", "symbol": alert.symbol}

        logger.info("All positions closed: %s %s", alert.exchange, alert.symbol)
        return self._order_to_dict(order)

    async def _cancel_orders(self, alert: AlertData, client: BaseExchange) -> dict[str, Any]:
        """Cancel all open orders for a symbol."""
        cancelled = await client.cancel_all_orders(alert.symbol)
        logger.info("Cancelled %d orders: %s %s", len(cancelled), alert.exchange, alert.symbol)
        return {"status": "cancelled", "cancelled_count": len(cancelled), "order_ids": cancelled}

    async def _set_stop_loss(self, alert: AlertData, client: BaseExchange) -> dict[str, Any]:
        """Set or modify stop-loss on an existing position."""
        if alert.stop_loss is None:
            raise ValueError("set_sl action requires 'stop_loss' field")

        position = await client.get_position(alert.symbol)
        if not position:
            raise ValueError(f"No open position found for {alert.symbol}")

        order = await client.set_stop_loss(alert.symbol, position.side, alert.stop_loss)
        logger.info("SL updated: %s %s @ %s", alert.exchange, alert.symbol, alert.stop_loss)
        return self._order_to_dict(order)

    async def _set_take_profit(self, alert: AlertData, client: BaseExchange) -> dict[str, Any]:
        """Set or modify take-profit on an existing position."""
        if alert.take_profit is None:
            raise ValueError("set_tp action requires 'take_profit' field")

        position = await client.get_position(alert.symbol)
        if not position:
            raise ValueError(f"No open position found for {alert.symbol}")

        order = await client.set_take_profit(alert.symbol, position.side, alert.take_profit)
        logger.info("TP updated: %s %s @ %s", alert.exchange, alert.symbol, alert.take_profit)
        return self._order_to_dict(order)

    async def _reverse_position(self, alert: AlertData, client: BaseExchange) -> dict[str, Any]:
        """Close current position and open opposite."""
        position = await client.get_position(alert.symbol)
        if position and position.size > 0:
            await client.cancel_all_orders(alert.symbol)
            await client.close_position(alert.symbol)
            logger.info("Reversed: closed %s position on %s", position.side, alert.symbol)

        # Open opposite
        if alert.action == "reverse":
            if position and position.side == "long":
                alert.action = "open_short"
            else:
                alert.action = "open_long"

        return await self._open_position(alert, client)

    async def _scale_in(self, alert: AlertData, client: BaseExchange) -> dict[str, Any]:
        """Add to an existing position."""
        position = await client.get_position(alert.symbol)
        if not position:
            logger.info("No existing position for scale_in, opening new: %s", alert.symbol)
            alert.action = "open_long"
            return await self._open_position(alert, client)

        side = "BUY" if position.side == "long" else "SELL"
        balance = await client.get_balance()
        current_price = await client.get_ticker_price(alert.symbol)

        quantity = self._sizer.calculate(
            balance=balance.available,
            current_price=current_price,
            size_type=alert.size_type,
            size_value=alert.size_value,
            stop_loss=alert.stop_loss,
            leverage=position.leverage,
        )

        order = await self._order_mgr.place_order(
            client=client,
            symbol=alert.symbol,
            side=side,
            quantity=quantity,
            order_type=alert.order_type,
            price=alert.price,
            leverage=None,  # Already set
        )

        logger.info("Scaled in: %s %s %s qty=%s", alert.exchange, side, alert.symbol, quantity)
        return self._order_to_dict(order, side=position.side)

    async def _scale_out(self, alert: AlertData, client: BaseExchange) -> dict[str, Any]:
        """Partially close a position (size_value = percentage to close)."""
        position = await client.get_position(alert.symbol)
        if not position or position.size == 0:
            return {"status": "no_position", "symbol": alert.symbol}

        close_percent = min(alert.size_value, 100.0) / 100.0
        close_qty = position.size * close_percent

        close_side = "SELL" if position.side == "long" else "BUY"

        order = await self._order_mgr.place_order(
            client=client,
            symbol=alert.symbol,
            side=close_side,
            quantity=close_qty,
            order_type=alert.order_type,
            price=alert.price,
        )

        logger.info(
            "Scaled out %.0f%%: %s %s %s qty=%s",
            alert.size_value, alert.exchange, close_side, alert.symbol, close_qty,
        )
        return self._order_to_dict(order, side=position.side)

    @staticmethod
    def _order_to_dict(order: OrderResult, side: str = "") -> dict[str, Any]:
        """Convert an OrderResult to a response dict."""
        return {
            "status": "executed",
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": side or order.side,
            "order_type": order.order_type,
            "quantity": order.quantity,
            "price": order.price,
            "exchange": order.exchange,
        }
