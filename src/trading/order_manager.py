"""
Order manager.
Handles order placement with retry logic, timeout handling,
and order status tracking.
"""

import asyncio
import logging
from typing import Any

from src.exchanges.base import BaseExchange, OrderResult

logger = logging.getLogger("trading.orders")


class OrderManager:
    """Manages order placement lifecycle with retries and error handling."""

    def __init__(self, trading_config: dict) -> None:
        self._retry_count = trading_config.get("retry_count", 3)
        self._retry_delay = trading_config.get("retry_delay_seconds", 1.0)
        self._timeout = trading_config.get("order_timeout_seconds", 30)

    async def place_order(
        self,
        client: BaseExchange,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
        leverage: int | None = None,
    ) -> OrderResult:
        """
        Place an order with retry logic.

        Args:
            client: Exchange client instance.
            symbol: Trading pair symbol.
            side: Order side (BUY or SELL).
            quantity: Order quantity.
            order_type: Order type (market, limit, stop).
            price: Limit/stop price (required for non-market orders).
            leverage: Leverage to set before placing order.

        Returns:
            OrderResult with execution details.

        Raises:
            RuntimeError: If all retry attempts fail.
        """
        last_error: Exception | None = None

        for attempt in range(1, self._retry_count + 1):
            try:
                order = await asyncio.wait_for(
                    self._execute_order(
                        client, symbol, side, quantity,
                        order_type, price, leverage,
                    ),
                    timeout=self._timeout,
                )
                if attempt > 1:
                    logger.info("Order succeeded on attempt %d", attempt)
                return order

            except asyncio.TimeoutError:
                last_error = RuntimeError(
                    f"Order timed out after {self._timeout}s"
                )
                logger.warning(
                    "Order attempt %d/%d timed out for %s %s %s",
                    attempt, self._retry_count, side, quantity, symbol,
                )

            except Exception as e:
                last_error = e
                logger.warning(
                    "Order attempt %d/%d failed: %s",
                    attempt, self._retry_count, e,
                )

            if attempt < self._retry_count:
                delay = self._retry_delay * attempt  # Exponential backoff
                logger.info("Retrying in %.1f seconds...", delay)
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Order failed after {self._retry_count} attempts: {last_error}"
        )

    async def _execute_order(
        self,
        client: BaseExchange,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        price: float | None,
        leverage: int | None,
    ) -> OrderResult:
        """Execute a single order attempt."""
        if order_type == "market":
            return await client.place_market_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                leverage=leverage,
            )
        elif order_type == "limit":
            if price is None:
                raise ValueError("Limit orders require a price")
            return await client.place_limit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                leverage=leverage,
            )
        elif order_type == "stop":
            if price is None:
                raise ValueError("Stop orders require a price")
            return await client.place_limit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                leverage=leverage,
            )
        else:
            raise ValueError(f"Unsupported order type: {order_type}")

    async def cancel_and_replace(
        self,
        client: BaseExchange,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
    ) -> OrderResult:
        """
        Cancel all existing orders for a symbol and place a new one.
        Useful for modifying existing limit/stop orders.
        """
        cancelled = await client.cancel_all_orders(symbol)
        if cancelled:
            logger.info(
                "Cancelled %d existing orders before replacement",
                len(cancelled),
            )
            # Brief delay to ensure cancellation is processed
            await asyncio.sleep(0.2)

        return await self.place_order(
            client=client,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
        )

    async def verify_order_filled(
        self,
        client: BaseExchange,
        symbol: str,
        order_id: str,
        max_wait: float = 10.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """
        Poll until a limit order is filled or timeout is reached.
        Returns True if filled, False if still open or timed out.
        """
        elapsed = 0.0
        while elapsed < max_wait:
            position = await client.get_position(symbol)
            if position and position.size > 0:
                logger.info("Order %s filled, position confirmed", order_id)
                return True
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning(
            "Order %s not confirmed after %.1fs", order_id, max_wait
        )
        return False
