"""
Bybit exchange client.
Supports Bybit V5 unified API for spot and linear (USDT) perpetuals.
"""

import hashlib
import hmac
import json
import logging
import time

from src.exchanges.base import BaseExchange, OrderResult, PositionInfo, BalanceInfo

logger = logging.getLogger("exchange.bybit")

BASE_URL = "https://api.bybit.com"
TESTNET_URL = "https://api-testnet.bybit.com"


class BybitClient(BaseExchange):
    """Bybit V5 API client."""

    EXCHANGE_NAME = "bybit"

    @property
    def base_url(self) -> str:
        return TESTNET_URL if self.testnet else BASE_URL

    @property
    def category(self) -> str:
        return "spot" if self.market_type == "spot" else "linear"

    def _sign_request(self, timestamp: str, params_str: str) -> str:
        """Generate Bybit V5 HMAC-SHA256 signature."""
        recv_window = "5000"
        pre_sign = f"{timestamp}{self.api_key}{recv_window}{params_str}"
        return hmac.new(
            self.api_secret.encode(), pre_sign.encode(), hashlib.sha256
        ).hexdigest()

    def _auth_headers(self, timestamp: str, signature: str) -> dict:
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": "5000",
            "Content-Type": "application/json",
        }

    async def _signed_get(self, path: str, params: dict | None = None) -> dict:
        params = params or {}
        timestamp = str(int(time.time() * 1000))
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = self._sign_request(timestamp, query)
        headers = self._auth_headers(timestamp, signature)
        url = f"{self.base_url}{path}"
        result = await self._request("GET", url, params=params, headers=headers)
        if result.get("retCode", -1) != 0:
            raise RuntimeError(f"Bybit API error: {result.get('retMsg', 'unknown')}")
        return result.get("result", {})

    async def _signed_post(self, path: str, payload: dict) -> dict:
        timestamp = str(int(time.time() * 1000))
        body_str = json.dumps(payload, separators=(",", ":"))
        signature = self._sign_request(timestamp, body_str)
        headers = self._auth_headers(timestamp, signature)
        url = f"{self.base_url}{path}"
        result = await self._request("POST", url, data=payload, headers=headers)
        if result.get("retCode", -1) != 0:
            raise RuntimeError(f"Bybit API error: {result.get('retMsg', 'unknown')}")
        return result.get("result", {})

    async def get_balance(self) -> BalanceInfo:
        result = await self._signed_get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        for account in result.get("list", []):
            for coin in account.get("coin", []):
                if coin.get("coin") == "USDT":
                    return BalanceInfo(
                        total=float(coin.get("walletBalance", 0)),
                        available=float(coin.get("availableToWithdraw", 0)),
                    )
        return BalanceInfo(total=0.0, available=0.0)

    async def get_position(self, symbol: str) -> PositionInfo | None:
        if self.market_type == "spot":
            return None

        result = await self._signed_get(
            "/v5/position/list", {"category": self.category, "symbol": symbol}
        )
        for pos in result.get("list", []):
            size = float(pos.get("size", 0))
            if size == 0:
                continue
            raw_side = pos.get("side", "").lower()
            side = "long" if raw_side == "buy" else "short"
            return PositionInfo(
                symbol=symbol,
                side=side,
                size=size,
                entry_price=float(pos.get("avgPrice", 0)),
                unrealized_pnl=float(pos.get("unrealisedPnl", 0)),
                leverage=int(float(pos.get("leverage", 1))),
                margin_type=pos.get("tradeMode", "cross"),
                liquidation_price=float(pos.get("liqPrice", 0)) or None,
            )
        return None

    async def place_market_order(
        self, symbol: str, side: str, quantity: float, leverage: int | None = None,
    ) -> OrderResult:
        if leverage and self.market_type != "spot":
            await self.set_leverage(symbol, leverage)

        payload = {
            "category": self.category,
            "symbol": symbol,
            "side": "Buy" if side.upper() == "BUY" else "Sell",
            "orderType": "Market",
            "qty": str(quantity),
        }

        result = await self._signed_post("/v5/order/create", payload)

        logger.info("Bybit market order: %s %s %s", side, quantity, symbol)

        return OrderResult(
            order_id=result.get("orderId", ""),
            symbol=symbol,
            side=side,
            order_type="market",
            quantity=quantity,
            price=None,
            status="NEW",
            exchange="bybit",
            raw=result,
        )

    async def place_limit_order(
        self, symbol: str, side: str, quantity: float, price: float,
        leverage: int | None = None,
    ) -> OrderResult:
        if leverage and self.market_type != "spot":
            await self.set_leverage(symbol, leverage)

        payload = {
            "category": self.category,
            "symbol": symbol,
            "side": "Buy" if side.upper() == "BUY" else "Sell",
            "orderType": "Limit",
            "qty": str(quantity),
            "price": str(price),
            "timeInForce": "GTC",
        }

        result = await self._signed_post("/v5/order/create", payload)

        logger.info("Bybit limit order: %s %s %s @ %s", side, quantity, symbol, price)

        return OrderResult(
            order_id=result.get("orderId", ""),
            symbol=symbol,
            side=side,
            order_type="limit",
            quantity=quantity,
            price=price,
            status="NEW",
            exchange="bybit",
            raw=result,
        )

    async def set_stop_loss(self, symbol: str, side: str, stop_price: float) -> OrderResult:
        payload = {
            "category": self.category,
            "symbol": symbol,
            "stopLoss": str(stop_price),
            "slTriggerBy": "LastPrice",
            "positionIdx": 0,
        }

        result = await self._signed_post("/v5/position/trading-stop", payload)
        logger.info("Bybit SL set: %s @ %s", symbol, stop_price)

        return OrderResult(
            order_id="sl_" + symbol,
            symbol=symbol,
            side=side,
            order_type="stop_loss",
            quantity=0,
            price=stop_price,
            status="SET",
            exchange="bybit",
            raw=result,
        )

    async def set_take_profit(self, symbol: str, side: str, tp_price: float) -> OrderResult:
        payload = {
            "category": self.category,
            "symbol": symbol,
            "takeProfit": str(tp_price),
            "tpTriggerBy": "LastPrice",
            "positionIdx": 0,
        }

        result = await self._signed_post("/v5/position/trading-stop", payload)
        logger.info("Bybit TP set: %s @ %s", symbol, tp_price)

        return OrderResult(
            order_id="tp_" + symbol,
            symbol=symbol,
            side=side,
            order_type="take_profit",
            quantity=0,
            price=tp_price,
            status="SET",
            exchange="bybit",
            raw=result,
        )

    async def cancel_all_orders(self, symbol: str) -> list[str]:
        try:
            result = await self._signed_post(
                "/v5/order/cancel-all",
                {"category": self.category, "symbol": symbol},
            )
            logger.info("Bybit: cancelled all orders for %s", symbol)
            return [o.get("orderId", "") for o in result.get("list", [])]
        except Exception as e:
            logger.error("Failed to cancel orders on Bybit: %s", e)
            return []

    async def close_position(self, symbol: str, side: str | None = None) -> OrderResult | None:
        position = await self.get_position(symbol)
        if not position or position.size == 0:
            logger.info("No position to close on %s", symbol)
            return None

        close_side = "SELL" if position.side == "long" else "BUY"
        return await self.place_market_order(symbol, close_side, position.size)

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        if self.market_type == "spot":
            return
        try:
            await self._signed_post(
                "/v5/position/set-leverage",
                {
                    "category": self.category,
                    "symbol": symbol,
                    "buyLeverage": str(leverage),
                    "sellLeverage": str(leverage),
                },
            )
            logger.info("Bybit leverage set: %s -> %dx", symbol, leverage)
        except Exception as e:
            logger.warning("Failed to set leverage on Bybit: %s", e)

    async def get_ticker_price(self, symbol: str) -> float:
        url = f"{self.base_url}/v5/market/tickers"
        result = await self._request(
            "GET", url, params={"category": self.category, "symbol": symbol}
        )
        tickers = result.get("result", {}).get("list", [])
        if tickers:
            return float(tickers[0].get("lastPrice", 0))
        return 0.0
