"""
Alert parser.
Converts raw TradingView webhook payloads (JSON or plain text) into
structured AlertData objects for the trade executor.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("webhook.parser")

VALID_ACTIONS = {
    "open_long", "open_short",
    "close_long", "close_short", "close_all",
    "cancel_orders",
    "set_sl", "set_tp",
    "reverse",
    "scale_in", "scale_out",
}

VALID_ORDER_TYPES = {"market", "limit", "stop"}
VALID_SIZE_TYPES = {"fixed", "percent", "risk", "kelly"}
VALID_EXCHANGES = {"binance", "bybit", "okx"}

# Pattern for plain text alerts:  EXCHANGE:SYMBOL ACTION [ORDER_TYPE] [SIZE%] [LEV:N] [SL:N] [TP:N]
_TEXT_PATTERN = re.compile(
    r"(?P<exchange>\w+):(?P<symbol>\w+)\s+"
    r"(?P<action>\w+)"
    r"(?:\s+(?P<order_type>MARKET|LIMIT|STOP))?"
    r"(?:\s+(?P<size>[\d.]+)%)?"
    r"(?:\s+LEV:(?P<leverage>\d+))?"
    r"(?:\s+SL:(?P<stop_loss>[\d.]+))?"
    r"(?:\s+TP:(?P<take_profit>[\d.]+))?",
    re.IGNORECASE,
)


@dataclass
class AlertData:
    """Structured alert data extracted from a TradingView webhook."""
    exchange: str
    symbol: str
    action: str
    order_type: str = "market"
    price: float | None = None
    size_type: str = "percent"
    size_value: float = 10.0
    leverage: int | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop: float | None = None
    account: str | None = None
    comment: str | None = None
    raw: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.exchange = self.exchange.lower()
        self.symbol = self.symbol.upper().replace("/", "").replace("-", "")
        self.action = self.action.lower()
        self.order_type = self.order_type.lower()
        self.size_type = self.size_type.lower()


def _parse_json_alert(data: dict) -> AlertData:
    """Parse a JSON alert payload into AlertData."""
    exchange = data.get("exchange", "")
    symbol = data.get("symbol", "")
    action = data.get("action", "")

    if not exchange:
        raise ValueError("Missing required field: 'exchange'")
    if not symbol:
        raise ValueError("Missing required field: 'symbol'")
    if not action:
        raise ValueError("Missing required field: 'action'")

    return AlertData(
        exchange=exchange,
        symbol=symbol,
        action=action,
        order_type=data.get("order_type", "market"),
        price=_to_float(data.get("price")),
        size_type=data.get("size_type", "percent"),
        size_value=float(data.get("size_value", 10.0)),
        leverage=_to_int(data.get("leverage")),
        stop_loss=_to_float(data.get("stop_loss")),
        take_profit=_to_float(data.get("take_profit")),
        trailing_stop=_to_float(data.get("trailing_stop")),
        account=data.get("account"),
        comment=data.get("comment"),
        raw=data,
    )


def _parse_text_alert(text: str) -> AlertData:
    """
    Parse a plain-text alert message.
    Format: EXCHANGE:SYMBOL ACTION [MARKET|LIMIT|STOP] [SIZE%] [LEV:N] [SL:N] [TP:N]
    Example: BINANCE:BTCUSDT OPEN_LONG MARKET 25% LEV:10 SL:42000 TP:48000
    """
    match = _TEXT_PATTERN.match(text.strip())
    if not match:
        raise ValueError(f"Could not parse plain-text alert: {text[:100]}")

    groups = match.groupdict()
    exchange = groups["exchange"]
    symbol = groups["symbol"]
    action = groups["action"]

    size_value = 10.0
    size_type = "percent"
    if groups.get("size"):
        size_value = float(groups["size"])
        size_type = "percent"

    return AlertData(
        exchange=exchange,
        symbol=symbol,
        action=action,
        order_type=groups.get("order_type") or "market",
        size_type=size_type,
        size_value=size_value,
        leverage=_to_int(groups.get("leverage")),
        stop_loss=_to_float(groups.get("stop_loss")),
        take_profit=_to_float(groups.get("take_profit")),
    )


def parse_alert(body: Any) -> AlertData:
    """
    Parse a webhook body into an AlertData object.
    Accepts both JSON (dict) and plain-text (str) payloads.
    """
    if isinstance(body, dict):
        alert = _parse_json_alert(body)
    elif isinstance(body, str):
        alert = _parse_text_alert(body)
    else:
        raise ValueError(f"Unsupported alert body type: {type(body)}")

    _validate_alert(alert)
    return alert


def _validate_alert(alert: AlertData) -> None:
    """Validate parsed alert fields."""
    if alert.exchange not in VALID_EXCHANGES:
        raise ValueError(
            f"Unsupported exchange '{alert.exchange}'. "
            f"Supported: {', '.join(sorted(VALID_EXCHANGES))}"
        )

    if alert.action not in VALID_ACTIONS:
        raise ValueError(
            f"Invalid action '{alert.action}'. "
            f"Supported: {', '.join(sorted(VALID_ACTIONS))}"
        )

    if alert.order_type not in VALID_ORDER_TYPES:
        raise ValueError(
            f"Invalid order_type '{alert.order_type}'. "
            f"Supported: {', '.join(sorted(VALID_ORDER_TYPES))}"
        )

    if alert.size_type not in VALID_SIZE_TYPES:
        raise ValueError(
            f"Invalid size_type '{alert.size_type}'. "
            f"Supported: {', '.join(sorted(VALID_SIZE_TYPES))}"
        )

    if alert.order_type == "limit" and alert.price is None:
        raise ValueError("Limit orders require a 'price' field")

    if alert.size_value <= 0:
        raise ValueError("size_value must be positive")

    if alert.leverage is not None and alert.leverage < 1:
        raise ValueError("leverage must be >= 1")


def _to_float(value: Any) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        result = float(value)
        return result if result > 0 else None
    except (ValueError, TypeError):
        return None


def _to_int(value: Any) -> int | None:
    """Safely convert a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None
