"""
Binance exchange client.
Supports both spot and USDT-M futures via the official REST API.
"""

import hashlib
import hmac
import logging
import time
from urllib.parse import urlencode

from src.exchanges.base import BaseExchange, OrderResult, PositionInfo, BalanceInfo

logger = logging.getLogger("exchange.binance")

FUTURES_BASE = "https://fapi.binance.com"
FUTURES_TESTNET = "https://testnet.binancefuture.com"
SPOT_BASE = "https://api.binance.com"
SPOT_TESTNET = "https://testnet.binance.vision"


class BinanceClient(BaseExchange):
    """Binance futures and spot client."""

    EXCHANGE_NAME = "binance"

    @property
    def base_url(self) -> str:
        if self.market_type == "spot":
            return SPOT_TESTNET if self.testnet else SPOT_BASE
        return FUTURES_TESTNET if self.testnet else FUTURES_BASE

    def _sign_params(self, params: dict) -> dict:
        """Add timestamp and HMAC-SHA256 signature to request params."""
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self.api_key}

    async def _signed_request(self, method: str, path: str, params: dict | None = None) -> dict:
        params = self._sign_params(params or {})
        url = f"{self.base_url}{path}"
        return await self._request(method, url, params=params, headers=self._headers())

    async def get_balance(self) -> BalanceInfo:
        if self.market_type == "spot":
            data = await self._signed_request("GET", "/api/v3/account")
            usdt = next(
                (b for b in data.get("balances", []) if b["asset"] == "USDT"),
                {"free": "0", "locked": "0"},
            )
            free = float(usdt["free"])
            locked = float(usdt["locked"])
            return BalanceInfo(total=free + locked, available=free)

        data = await self._signed_request("GET", "/fapi/v2/balance")
        for asset in data:
            if asset.get("asset") == "USDT":
                return BalanceInfo(
                    total=float(asset["balance"]),
                    available=float(asset["availableBalance"]),
                )
        return BalanceInfo(total=0.0, available=0.0)

    async def get_position(self, symbol: str) -> PositionInfo | None:
        if self.market_type == "spot":
            return None

        data = await self._signed_request("GET", "/fapi/v2/positionRisk", {"symbol": symbol})
        for pos in data:
            size = float(pos.get("positionAmt", 0))
            if size == 0:
                continue
            side = "long" if size > 0 else "short"
            return PositionInfo(
                symbol=symbol,
                side=side,
                size=abs(size),
                entry_price=float(pos.get("entryPrice", 0)),
                unrealized_pnl=float(pos.get("unRealizedProfit", 0)),
                leverage=int(pos.get("leverage", 1)),
                margin_type=pos.get("marginType", "cross"),
                liquidation_price=float(pos.get("liquidationPrice", 0)) or None,
            )
        return None

    async def place_market_order(
        self, symbol: str, side: str, quantity: float, leverage: int | None = None,
    ) -> OrderResult:
        if leverage and self.market_type == "futures":
            await self.set_leverage(symbol, leverage)

        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": f"{quantity:.8f}".rstrip("0").rstrip("."),
        }

        if self.market_type == "futures":
            path = "/fapi/v1/order"
        else:
            path = "/api/v3/order"

        result = await self._signed_request("POST", path, params)
        avg_price = float(result.get("avgPrice", 0)) or float(result.get("price", 0))

        logger.info("Binance market order placed: %s %s %s @ %s", side, quantity, symbol, avg_price)

        return OrderResult(
            order_id=str(result.get("orderId", "")),
            symbol=symbol,
            side=side,
            order_type="market",
            quantity=quantity,
            price=avg_price,
            status=result.get("status", "UNKNOWN"),
            exchange="binance",
            raw=result,
        )

    async def place_limit_order(
        self, symbol: str, side: str, quantity: float, price: float,
        leverage: int | None = None,
    ) -> OrderResult:
        if leverage and self.market_type == "futures":
            await self.set_leverage(symbol, leverage)

        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": f"{quantity:.8f}".rstrip("0").rstrip("."),
            "price": f"{price:.8f}".rstrip("0").rstrip("."),
        }

        path = "/fapi/v1/order" if self.market_type == "futures" else "/api/v3/order"
        result = await self._signed_request("POST", path, params)

        logger.info("Binance limit order placed: %s %s %s @ %s", side, quantity, symbol, price)

        return OrderResult(
            order_id=str(result.get("orderId", "")),
            symbol=symbol,
            side=side,
            order_type="limit",
            quantity=quantity,
            price=price,
            status=result.get("status", "UNKNOWN"),
            exchange="binance",
            raw=result,
        )

    async def set_stop_loss(self, symbol: str, side: str, stop_price: float) -> OrderResult:
        close_side = "SELL" if side.lower() == "long" else "BUY"
        params = {
            "symbol": symbol,
            "side": close_side,
            "type": "STOP_MARKET",
            "closePosition": "true",
            "stopPrice": f"{stop_price:.8f}".rstrip("0").rstrip("."),
        }

        path = "/fapi/v1/order" if self.market_type == "futures" else "/api/v3/order"
        result = await self._signed_request("POST", path, params)

        logger.info("Binance SL set: %s %s @ %s", symbol, close_side, stop_price)

        return OrderResult(
            order_id=str(result.get("orderId", "")),
            symbol=symbol,
            side=close_side,
            order_type="stop_market",
            quantity=0,
            price=stop_price,
            status=result.get("status", "UNKNOWN"),
            exchange="binance",
            raw=result,
        )

    async def set_take_profit(self, symbol: str, side: str, tp_price: float) -> OrderResult:
        close_side = "SELL" if side.lower() == "long" else "BUY"
        params = {
            "symbol": symbol,
            "side": close_side,
            "type": "TAKE_PROFIT_MARKET",
            "closePosition": "true",
            "stopPrice": f"{tp_price:.8f}".rstrip("0").rstrip("."),
        }

        path = "/fapi/v1/order" if self.market_type == "futures" else "/api/v3/order"
        result = await self._signed_request("POST", path, params)

        logger.info("Binance TP set: %s %s @ %s", symbol, close_side, tp_price)

        return OrderResult(
            order_id=str(result.get("orderId", "")),
            symbol=symbol,
            side=close_side,
            order_type="take_profit_market",
            quantity=0,
            price=tp_price,
            status=result.get("status", "UNKNOWN"),
            exchange="binance",
            raw=result,
        )

    async def cancel_all_orders(self, symbol: str) -> list[str]:
        path = "/fapi/v1/allOpenOrders" if self.market_type == "futures" else "/api/v3/openOrders"
        try:
            result = await self._signed_request("DELETE", path, {"symbol": symbol})
            logger.info("Binance: cancelled all orders for %s", symbol)
            if isinstance(result, list):
                return [str(o.get("orderId", "")) for o in result]
            return []
        except Exception as e:
            logger.error("Failed to cancel orders on Binance: %s", e)
            return []

    async def close_position(self, symbol: str, side: str | None = None) -> OrderResult | None:
        position = await self.get_position(symbol)
        if not position or position.size == 0:
            logger.info("No position to close on %s", symbol)
            return None

        close_side = "SELL" if position.side == "long" else "BUY"
        return await self.place_market_order(symbol, close_side, position.size)

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        if self.market_type != "futures":
            return
        try:
            await self._signed_request(
                "POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage}
            )
            logger.info("Binance leverage set: %s -> %dx", symbol, leverage)
        except Exception as e:
            logger.warning("Failed to set leverage on Binance: %s", e)

    async def get_ticker_price(self, symbol: str) -> float:
        path = "/fapi/v1/ticker/price" if self.market_type == "futures" else "/api/v3/ticker/price"
        url = f"{self.base_url}{path}"
        result = await self._request("GET", url, params={"symbol": symbol})
        return float(result.get("price", 0))
