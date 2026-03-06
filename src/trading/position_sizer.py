"""
Position sizer.
Calculates trade quantity based on various sizing methods:
fixed, percent, risk-based, and Kelly criterion.
"""

import logging
import math

logger = logging.getLogger("trading.sizer")


class PositionSizer:
    """Calculates position sizes using different methodologies."""

    def __init__(self, risk_config: dict) -> None:
        self._config = risk_config

    def calculate(
        self,
        balance: float,
        current_price: float,
        size_type: str = "percent",
        size_value: float = 10.0,
        stop_loss: float | None = None,
        leverage: int = 1,
        win_rate: float | None = None,
        avg_win: float | None = None,
        avg_loss: float | None = None,
    ) -> float:
        """
        Calculate position quantity based on the sizing method.

        Args:
            balance: Available account balance in USDT.
            current_price: Current price of the asset.
            size_type: Sizing method (fixed, percent, risk, kelly).
            size_value: Value parameter for the sizing method.
            stop_loss: Stop-loss price (required for risk-based sizing).
            leverage: Position leverage multiplier.
            win_rate: Historical win rate (for Kelly criterion).
            avg_win: Average winning trade (for Kelly criterion).
            avg_loss: Average losing trade (for Kelly criterion).

        Returns:
            Position quantity (number of contracts/coins).
        """
        if balance <= 0 or current_price <= 0:
            logger.warning("Invalid balance (%.2f) or price (%.2f)", balance, current_price)
            return 0.0

        methods = {
            "fixed": self._fixed_size,
            "percent": self._percent_size,
            "risk": self._risk_based_size,
            "kelly": self._kelly_size,
        }

        method = methods.get(size_type)
        if method is None:
            logger.warning("Unknown size_type '%s', falling back to percent", size_type)
            method = self._percent_size

        quantity = method(
            balance=balance,
            current_price=current_price,
            size_value=size_value,
            stop_loss=stop_loss,
            leverage=leverage,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
        )

        # Apply leverage
        quantity *= leverage

        # Enforce minimum order value
        min_value = self._config.get("min_order_value", 10.0)
        notional = quantity * current_price
        if notional < min_value:
            logger.warning(
                "Calculated order value $%.2f below minimum $%.2f",
                notional, min_value,
            )
            quantity = min_value / current_price

        # Round to reasonable precision
        quantity = self._round_quantity(quantity, current_price)

        logger.info(
            "Position size: method=%s value=%.2f balance=%.2f price=%.2f "
            "leverage=%dx -> qty=%.8f (notional=$%.2f)",
            size_type, size_value, balance, current_price,
            leverage, quantity, quantity * current_price,
        )

        return quantity

    def _fixed_size(self, balance: float, current_price: float,
                    size_value: float, **kwargs) -> float:
        """Fixed USDT amount. size_value = dollar amount."""
        return size_value / current_price

    def _percent_size(self, balance: float, current_price: float,
                      size_value: float, leverage: int = 1, **kwargs) -> float:
        """Percentage of balance. size_value = percentage (e.g., 25 for 25%)."""
        pct = min(size_value, 100.0) / 100.0
        usdt_amount = balance * pct
        return usdt_amount / current_price

    def _risk_based_size(
        self, balance: float, current_price: float,
        size_value: float, stop_loss: float | None = None,
        leverage: int = 1, **kwargs,
    ) -> float:
        """
        Risk-based sizing.
        size_value = risk percentage of balance.
        Requires a stop_loss price to calculate position size.
        Formula: qty = (balance * risk%) / |entry - stop_loss|
        """
        if stop_loss is None or stop_loss <= 0:
            logger.warning("Risk-based sizing requires stop_loss, falling back to 1%% of balance")
            return (balance * 0.01) / current_price

        risk_amount = balance * (size_value / 100.0)
        price_distance = abs(current_price - stop_loss)

        if price_distance == 0:
            logger.warning("Stop loss equals current price, cannot calculate risk-based size")
            return (balance * 0.01) / current_price

        quantity = risk_amount / price_distance

        # Cap at max single trade percentage
        max_pct = self._config.get("max_single_trade_percent", 50.0) / 100.0
        max_qty = (balance * max_pct) / current_price
        if quantity > max_qty:
            logger.info("Risk-based size capped at max_single_trade_percent")
            quantity = max_qty

        return quantity

    def _kelly_size(
        self, balance: float, current_price: float,
        size_value: float, win_rate: float | None = None,
        avg_win: float | None = None, avg_loss: float | None = None,
        **kwargs,
    ) -> float:
        """
        Kelly criterion sizing.
        size_value = Kelly fraction (e.g., 0.5 for half-Kelly).
        Uses historical win rate and avg win/loss ratio.
        Falls back to conservative defaults if stats unavailable.
        """
        # Default conservative estimates if no historical data
        p = win_rate if win_rate is not None else 0.55  # Win probability
        b = 1.5  # Win/loss ratio

        if avg_win and avg_loss and avg_loss > 0:
            b = avg_win / avg_loss

        # Kelly formula: f* = p - (1-p)/b
        kelly_pct = p - (1 - p) / b

        # Apply Kelly fraction (e.g., half-Kelly)
        kelly_fraction = min(max(size_value, 0.1), 1.0)
        adjusted_pct = kelly_pct * kelly_fraction

        # Clamp to reasonable range [0.5%, 25%]
        adjusted_pct = max(0.005, min(adjusted_pct, 0.25))

        usdt_amount = balance * adjusted_pct
        quantity = usdt_amount / current_price

        logger.info(
            "Kelly sizing: win_rate=%.2f, b=%.2f, kelly=%.4f, "
            "fraction=%.2f, adjusted=%.4f",
            p, b, kelly_pct, kelly_fraction, adjusted_pct,
        )

        return quantity

    @staticmethod
    def _round_quantity(quantity: float, price: float) -> float:
        """
        Round quantity to appropriate precision based on price.
        Higher-priced assets get more decimal places for quantity.
        """
        if price >= 10000:
            decimals = 5
        elif price >= 100:
            decimals = 4
        elif price >= 1:
            decimals = 2
        else:
            decimals = 0

        factor = 10 ** decimals
        return math.floor(quantity * factor) / factor
