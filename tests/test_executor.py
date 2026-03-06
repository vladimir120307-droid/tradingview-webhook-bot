"""
Tests for the trade executor.
Uses mock exchange clients to verify order placement logic.
"""

import pytest
import pytest_asyncio

from src.exchanges.base import BaseExchange, OrderResult, PositionInfo, BalanceInfo
from src.trading.executor import TradeExecutor
from src.trading.order_manager import OrderManager
from src.webhook.parser import AlertData


class MockExchangeClient(BaseExchange):
    """Mock exchange client for testing."""

    EXCHANGE_NAME = "mock"

    def __init__(self):
        super().__init__(api_key="test", api_secret="test")
        self._balance = BalanceInfo(total=10000.0, available=8000.0)
        self._position: PositionInfo | None = None
        self._ticker_price = 45000.0
        self._orders: list[OrderResult] = []
        self._leverage_set: dict[str, int] = {}

    async def initialize(self):
        pass

    async def get_balance(self) -> BalanceInfo:
        return self._balance

    async def get_position(self, symbol: str) -> PositionInfo | None:
        return self._position

    async def place_market_order(
        self, symbol: str, side: str, quantity: float, leverage: int | None = None,
    ) -> OrderResult:
        order = OrderResult(
            order_id="mock_order_1",
            symbol=symbol,
            side=side,
            order_type="market",
            quantity=quantity,
            price=self._ticker_price,
            status="FILLED",
            exchange="mock",
        )
        self._orders.append(order)
        return order

    async def place_limit_order(
        self, symbol: str, side: str, quantity: float, price: float,
        leverage: int | None = None,
    ) -> OrderResult:
        order = OrderResult(
            order_id="mock_limit_1",
            symbol=symbol,
            side=side,
            order_type="limit",
            quantity=quantity,
            price=price,
            status="NEW",
            exchange="mock",
        )
        self._orders.append(order)
        return order

    async def set_stop_loss(self, symbol: str, side: str, stop_price: float) -> OrderResult:
        return OrderResult(
            order_id="mock_sl_1", symbol=symbol, side=side,
            order_type="stop_market", quantity=0, price=stop_price,
            status="SET", exchange="mock",
        )

    async def set_take_profit(self, symbol: str, side: str, tp_price: float) -> OrderResult:
        return OrderResult(
            order_id="mock_tp_1", symbol=symbol, side=side,
            order_type="take_profit", quantity=0, price=tp_price,
            status="SET", exchange="mock",
        )

    async def cancel_all_orders(self, symbol: str) -> list[str]:
        ids = [o.order_id for o in self._orders]
        self._orders.clear()
        return ids

    async def close_position(self, symbol: str, side: str | None = None) -> OrderResult | None:
        if not self._position or self._position.size == 0:
            return None
        close_side = "SELL" if self._position.side == "long" else "BUY"
        order = await self.place_market_order(symbol, close_side, self._position.size)
        self._position = None
        return order

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        self._leverage_set[symbol] = leverage

    async def get_ticker_price(self, symbol: str) -> float:
        return self._ticker_price


class MockSettings:
    """Minimal mock settings for the executor."""

    def __init__(self):
        self._risk = {
            "default_leverage": 1,
            "max_leverage": 50,
            "min_order_value": 10,
            "max_single_trade_percent": 50,
            "default_size_type": "percent",
            "default_size_value": 10,
        }
        self._trading = {
            "retry_count": 1,
            "retry_delay_seconds": 0.1,
            "order_timeout_seconds": 5,
        }

    @property
    def risk(self):
        return self._risk

    @property
    def trading(self):
        return self._trading


@pytest.fixture
def mock_client():
    return MockExchangeClient()


@pytest.fixture
def executor():
    return TradeExecutor(MockSettings())


@pytest.mark.asyncio
async def test_open_long(executor, mock_client):
    alert = AlertData(
        exchange="mock",
        symbol="BTCUSDT",
        action="open_long",
        size_type="percent",
        size_value=10.0,
    )
    result = await executor.execute(alert, mock_client)
    assert result["status"] == "executed"
    assert result["side"] == "long"
    assert result["symbol"] == "BTCUSDT"
    assert result["quantity"] > 0


@pytest.mark.asyncio
async def test_open_short(executor, mock_client):
    alert = AlertData(
        exchange="mock",
        symbol="ETHUSDT",
        action="open_short",
        size_type="fixed",
        size_value=500.0,
    )
    mock_client._ticker_price = 3500.0
    result = await executor.execute(alert, mock_client)
    assert result["status"] == "executed"
    assert result["side"] == "short"


@pytest.mark.asyncio
async def test_close_long_no_position(executor, mock_client):
    alert = AlertData(
        exchange="mock",
        symbol="BTCUSDT",
        action="close_long",
    )
    result = await executor.execute(alert, mock_client)
    assert result["status"] == "no_position"


@pytest.mark.asyncio
async def test_close_long_with_position(executor, mock_client):
    mock_client._position = PositionInfo(
        symbol="BTCUSDT",
        side="long",
        size=0.1,
        entry_price=44000,
        unrealized_pnl=100,
        leverage=5,
        margin_type="cross",
    )
    alert = AlertData(
        exchange="mock",
        symbol="BTCUSDT",
        action="close_long",
    )
    result = await executor.execute(alert, mock_client)
    assert result["status"] == "executed"
    assert result["quantity"] == 0.1


@pytest.mark.asyncio
async def test_open_with_sl_tp(executor, mock_client):
    alert = AlertData(
        exchange="mock",
        symbol="BTCUSDT",
        action="open_long",
        size_type="percent",
        size_value=20.0,
        stop_loss=43000.0,
        take_profit=48000.0,
    )
    result = await executor.execute(alert, mock_client)
    assert result["status"] == "executed"
    assert result.get("stop_loss") == 43000.0
    assert result.get("take_profit") == 48000.0


@pytest.mark.asyncio
async def test_cancel_orders(executor, mock_client):
    # Place some orders first
    await mock_client.place_market_order("BTCUSDT", "BUY", 0.1)
    assert len(mock_client._orders) == 1

    alert = AlertData(
        exchange="mock",
        symbol="BTCUSDT",
        action="cancel_orders",
    )
    result = await executor.execute(alert, mock_client)
    assert result["status"] == "cancelled"


@pytest.mark.asyncio
async def test_scale_out(executor, mock_client):
    mock_client._position = PositionInfo(
        symbol="BTCUSDT",
        side="long",
        size=1.0,
        entry_price=44000,
        unrealized_pnl=500,
        leverage=5,
        margin_type="cross",
    )
    alert = AlertData(
        exchange="mock",
        symbol="BTCUSDT",
        action="scale_out",
        size_value=50.0,  # Close 50%
    )
    result = await executor.execute(alert, mock_client)
    assert result["status"] == "executed"
    assert result["quantity"] == 0.5
