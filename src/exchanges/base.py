"""
Abstract base class for exchange clients.
All exchange implementations must inherit from BaseExchange.
"""

import asyncio
import hashlib
import hmac
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("exchange.base")


@dataclass
class OrderResult:
    """Standardized order result returned by all exchange clients."""
    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float | None
    status: str
    exchange: str
    raw: dict = field(default_factory=dict)

    @property
    def filled(self) -> bool:
        return self.status.lower() in ("filled", "new", "partially_filled")


@dataclass
class PositionInfo:
    """Standardized position info."""
    symbol: str
    side: str               # "long" | "short" | "none"
    size: float
    entry_price: float
    unrealized_pnl: float
    leverage: int
    margin_type: str
    liquidation_price: float | None = None


@dataclass
class BalanceInfo:
    """Account balance info."""
    total: float
    available: float
    currency: str = "USDT"


class BaseExchange(ABC):
    """Abstract exchange client with common functionality."""

    EXCHANGE_NAME: str = "base"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str | None = None,
        testnet: bool = False,
        market_type: str = "futures",
        margin_type: str = "cross",
        default_leverage: int = 1,
        rate_limit: int = 10,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.testnet = testnet
        self.market_type = market_type
        self.margin_type = margin_type
        self.default_leverage = default_leverage
        self._rate_limit = rate_limit
        self._last_request_time = 0.0
        self._http: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        """Set up the HTTP client and any exchange-specific initialization."""
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        logger.info("%s client initialized (testnet=%s)", self.EXCHANGE_NAME, self.testnet)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http:
            await self._http.aclose()
            self._http = None

    async def _rate_limit_wait(self) -> None:
        """Simple rate limiting between requests."""
        min_interval = 1.0 / self._rate_limit
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def _sign_hmac_sha256(self, message: str) -> str:
        """HMAC-SHA256 signature."""
        return hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def _request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        data: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        """Make an authenticated HTTP request with rate limiting."""
        await self._rate_limit_wait()

        if self._http is None:
            raise RuntimeError(f"{self.EXCHANGE_NAME} client not initialized")

        try:
            response = await self._http.request(
                method=method,
                url=url,
                params=params,
                json=data,
                headers=headers or {},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "%s API error: %s %s -> %s",
                self.EXCHANGE_NAME, method, url, e.response.text,
            )
            raise
        except httpx.RequestError as e:
            logger.error("%s request failed: %s", self.EXCHANGE_NAME, e)
            raise

    @abstractmethod
    async def get_balance(self) -> BalanceInfo:
        """Get account balance."""
        ...

    @abstractmethod
    async def get_position(self, symbol: str) -> PositionInfo | None:
        """Get current position for a symbol."""
        ...

    @abstractmethod
    async def place_market_order(
        self, symbol: str, side: str, quantity: float, leverage: int | None = None,
    ) -> OrderResult:
        """Place a market order."""
        ...

    @abstractmethod
    async def place_limit_order(
        self, symbol: str, side: str, quantity: float, price: float,
        leverage: int | None = None,
    ) -> OrderResult:
        """Place a limit order."""
        ...

    @abstractmethod
    async def set_stop_loss(self, symbol: str, side: str, stop_price: float) -> OrderResult:
        """Set a stop-loss order for an existing position."""
        ...

    @abstractmethod
    async def set_take_profit(self, symbol: str, side: str, tp_price: float) -> OrderResult:
        """Set a take-profit order for an existing position."""
        ...

    @abstractmethod
    async def cancel_all_orders(self, symbol: str) -> list[str]:
        """Cancel all open orders for a symbol. Returns list of cancelled order IDs."""
        ...

    @abstractmethod
    async def close_position(self, symbol: str, side: str | None = None) -> OrderResult | None:
        """Close an open position."""
        ...

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> None:
        """Set leverage for a symbol."""
        ...

    @abstractmethod
    async def get_ticker_price(self, symbol: str) -> float:
        """Get the current price of a symbol."""
        ...
