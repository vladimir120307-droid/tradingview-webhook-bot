"""
Utility helper functions.
Common operations used across the application.
"""

import hashlib
import math
import secrets
import string
from datetime import datetime, timezone
from typing import Any


def generate_secret(length: int = 32) -> str:
    """Generate a cryptographically secure random secret string."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def timestamp_ms() -> int:
    """Get the current UTC timestamp in milliseconds."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def timestamp_iso() -> str:
    """Get the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def round_price(price: float, tick_size: float = 0.01) -> float:
    """
    Round a price to the nearest tick size.

    Args:
        price: The price to round.
        tick_size: Minimum price increment.

    Returns:
        Rounded price value.
    """
    if tick_size <= 0:
        return price
    precision = max(0, -int(math.log10(tick_size)))
    return round(round(price / tick_size) * tick_size, precision)


def round_quantity(quantity: float, step_size: float = 0.001) -> float:
    """
    Round a quantity to the nearest step size (floor).

    Args:
        quantity: The quantity to round.
        step_size: Minimum quantity increment.

    Returns:
        Rounded (floored) quantity value.
    """
    if step_size <= 0:
        return quantity
    precision = max(0, -int(math.log10(step_size)))
    return math.floor(quantity / step_size) * step_size


def calculate_pnl(
    entry_price: float,
    exit_price: float,
    quantity: float,
    side: str,
    leverage: int = 1,
) -> float:
    """
    Calculate realized P&L for a closed position.

    Args:
        entry_price: Position entry price.
        exit_price: Position exit price.
        quantity: Position size.
        side: Position side (long/short).
        leverage: Position leverage.

    Returns:
        Realized P&L in quote currency (USDT).
    """
    if side.lower() == "long":
        pnl = (exit_price - entry_price) * quantity
    else:
        pnl = (entry_price - exit_price) * quantity

    return pnl


def calculate_roi(
    entry_price: float,
    exit_price: float,
    side: str,
    leverage: int = 1,
) -> float:
    """
    Calculate return on investment percentage.

    Args:
        entry_price: Position entry price.
        exit_price: Position exit price.
        side: Position side (long/short).
        leverage: Position leverage.

    Returns:
        ROI as a percentage.
    """
    if entry_price <= 0:
        return 0.0

    if side.lower() == "long":
        roi = ((exit_price - entry_price) / entry_price) * 100
    else:
        roi = ((entry_price - exit_price) / entry_price) * 100

    return roi * leverage


def format_number(value: float, decimals: int = 2) -> str:
    """Format a number with thousands separators and fixed decimals."""
    return f"{value:,.{decimals}f}"


def format_currency(value: float) -> str:
    """Format a value as USD currency."""
    if value >= 0:
        return f"${value:,.2f}"
    return f"-${abs(value):,.2f}"


def format_percent(value: float) -> str:
    """Format a value as a percentage with sign."""
    return f"{value:+.2f}%"


def sanitize_symbol(symbol: str) -> str:
    """
    Normalize a trading symbol.
    Removes slashes, dashes, and converts to uppercase.
    """
    return symbol.upper().replace("/", "").replace("-", "").replace("_", "").strip()


def parse_side_from_action(action: str) -> str:
    """
    Extract the trade side from an action string.

    Args:
        action: Alert action (e.g., 'open_long', 'close_short').

    Returns:
        'long', 'short', or 'unknown'.
    """
    action = action.lower()
    if "long" in action:
        return "long"
    if "short" in action:
        return "short"
    return "unknown"


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float with a default fallback."""
    if value is None:
        return default
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert a value to int with a default fallback."""
    if value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def hash_string(text: str) -> str:
    """Generate a SHA-256 hash of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
