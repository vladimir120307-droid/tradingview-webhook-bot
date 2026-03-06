"""
OKX exchange client.
Supports OKX V5 API for spot and USDT-margined swaps (perpetuals).
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone

from src.exchanges.base import BaseExchange, OrderResult, PositionInfo, BalanceInfo

logger = logging.getLogger("exchange.okx")

BASE_URL = "https://www.okx.com"
TESTNET_URL = "https://www.okx.com"  # OKX uses a flag, not a separate URL


class OKXClient(BaseExchange):
    """OKX V5 API client."""

    EXCHANGE_NAME = "okx"

    @property
    def base_url(self) -> str:
        return BASE_URL

    @property
    def inst_type(self) -> str:
        return "SPOT" if self.market_type == "spot" else "SWAP"

    @property
    def td_mode(self) -> str:
        if self.market_type == "spot":
            return "cash"
        return "cross" if self.margin_type == "cross" else "isolated"

    def _generate_signature(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """OKX HMAC-SHA256 signature with Base64 encoding."""
        pre_sign = f"{timestamp}{method.upper()}{path}{body}"
        mac = hmac.new(self.api_secret.encode(), pre_sign.encode(), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _auth_headers(self, method: str, path: str, body: str = "") -> dict:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        signature = self._generate_signature(timestamp, method, path, body)
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase or "",
            "Content-Type": "application/json",
        }
        if self.testnet:
            headers["x-simulated-trading"] = "1"
        return headers

    async def _signed_get(self, path: str, params: dict | None = None) -> list:
        query = ""
        if params:
            query = "?" + "&".join(f"{k}={v}" for k, v in params.items())
        full_path = path + query
        headers = self._auth_headers("GET", full_path)
        url = f"{self.base_url}{full_path}"
        result = await self._request("GET", url, headers=headers)
        if result.get("code") != "0":
            raise RuntimeError(f"OKX API error: {result.get('msg', 'unknown')}")
        return result.get("data", [])

    async def _signed_post(self, path: str, payload: dict) -> list:
        body = json.dumps(payload, separators=(",", ":"))
        headers = self._auth_headers("POST", path, body)
        url = f"{self.base_url}{path}"
        result = await self._request("POST", url, data=payload, headers=headers)
        if result.get("code") != "0":
            msg = result.get("data", [{}])[0].get("sMsg", result.get("msg", "unknown"))
            raise RuntimeError(f"OKX API error: {msg}")
        return result.get("data", [])

    def _to_inst_id(self, symbol: str) -> str:
        """Convert BTCUSDT -> BTC-USDT-SWAP or BTC-USDT for spot."""
        clean = symbol.upper().replace("-", "").replace("/", "")
        if clean.endswith("USDT"):
            base = clean[:-4]
            if self.market_type == "spot":
                return f"{base}-USDT"
            return f"{base}-USDT-SWAP"
        return symbol

    async def get_balance(self) -> BalanceInfo:
        data = await self._signed_get("/api/v5/account/balance", {"ccy": "USDT"})
        if data:
            details = data[0].get("details", [])
            for d in details:
                if d.get("ccy") == "USDT":
                    return BalanceInfo(
                        total=float(d.get("eq", 0)),
                        available=float(d.get("availBal", 0)),
                    )
        return BalanceInfo(total=0.0, available=0.0)

    async def get_position(self, symbol: str) -> PositionInfo | None:
        if self.market_type == "spot":
            return None

        inst_id = self._to_inst_id(symbol)
        data = await self._signed_get("/api/v5/account/positions", {"instId": inst_id})
        for pos in data:
            size = float(pos.get("pos", 0))
            if size == 0:
                continue
            raw_side = pos.get("posSide", "net")
            if raw_side == "net":
                side = "long" if size > 0 else "short"
            else:
                side = raw_side.lower()
            return PositionInfo(
                symbol=symbol,
                side=side,
                size=abs(size),
                entry_price=float(pos.get("avgPx", 0)),
                unrealized_pnl=float(pos.get("upl", 0)),
                leverage=int(float(pos.get("lever", 1))),
                margin_type=pos.get("mgnMode", "cross"),
                liquidation_price=float(pos.get("liqPx", 0)) or None,
            )
        return None

    async def place_market_order(
        self, symbol: str, side: str, quantity: float, leverage: int | None = None,
    ) -> OrderResult:
        inst_id = self._to_inst_id(symbol)

        if leverage and self.market_type != "spot":
            await self.set_leverage(symbol, leverage)

        payload = {
            "instId": inst_id,
            "tdMode": self.td_mode,
            "side": side.lower(),
            "ordType": "market",
            "sz": str(quantity),
        }

        data = await self._signed_post("/api/v5/trade/order", payload)
        order_id = data[0].get("ordId", "") if data else ""

        logger.info("OKX market order: %s %s %s", side, quantity, inst_id)

        return OrderResult(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type="market",
            quantity=quantity,
            price=None,
            status="NEW",
            exchange="okx",
            raw=data[0] if data else {},
        )

    async def place_limit_order(
        self, symbol: str, side: str, quantity: float, price: float,
        leverage: int | None = None,
    ) -> OrderResult:
        inst_id = self._to_inst_id(symbol)

        if leverage and self.market_type != "spot":
            await self.set_leverage(symbol, leverage)

        payload = {
            "instId": inst_id,
            "tdMode": self.td_mode,
            "side": side.lower(),
            "ordType": "limit",
            "px": str(price),
            "sz": str(quantity),
        }

        data = await self._signed_post("/api/v5/trade/order", payload)
        order_id = data[0].get("ordId", "") if data else ""

        logger.info("OKX limit order: %s %s %s @ %s", side, quantity, inst_id, price)

        return OrderResult(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type="limit",
            quantity=quantity,
            price=price,
            status="NEW",
            exchange="okx",
            raw=data[0] if data else {},
        )

    async def set_stop_loss(self, symbol: str, side: str, stop_price: float) -> OrderResult:
        inst_id = self._to_inst_id(symbol)
        close_side = "sell" if side.lower() == "long" else "buy"

        payload = {
            "instId": inst_id,
            "tdMode": self.td_mode,
            "side": close_side,
            "ordType": "trigger",
            "triggerPx": str(stop_price),
            "orderPx": "-1",
            "sz": "0",
            "reduceOnly": True,
            "triggerPxType": "last",
        }

        data = await self._signed_post("/api/v5/trade/order-algo", payload)
        logger.info("OKX SL set: %s @ %s", inst_id, stop_price)

        return OrderResult(
            order_id=data[0].get("algoId", "") if data else "",
            symbol=symbol,
            side=close_side,
            order_type="stop_loss",
            quantity=0,
            price=stop_price,
            status="SET",
            exchange="okx",
            raw=data[0] if data else {},
        )

    async def set_take_profit(self, symbol: str, side: str, tp_price: float) -> OrderResult:
        inst_id = self._to_inst_id(symbol)
        close_side = "sell" if side.lower() == "long" else "buy"

        payload = {
            "instId": inst_id,
            "tdMode": self.td_mode,
            "side": close_side,
            "ordType": "trigger",
            "triggerPx": str(tp_price),
            "orderPx": "-1",
            "sz": "0",
            "reduceOnly": True,
            "triggerPxType": "last",
        }

        data = await self._signed_post("/api/v5/trade/order-algo", payload)
        logger.info("OKX TP set: %s @ %s", inst_id, tp_price)

        return OrderResult(
            order_id=data[0].get("algoId", "") if data else "",
            symbol=symbol,
            side=close_side,
            order_type="take_profit",
            quantity=0,
            price=tp_price,
            status="SET",
            exchange="okx",
            raw=data[0] if data else {},
        )

    async def cancel_all_orders(self, symbol: str) -> list[str]:
        inst_id = self._to_inst_id(symbol)
        try:
            # Get open orders first
            open_orders = await self._signed_get(
                "/api/v5/trade/orders-pending", {"instId": inst_id}
            )
            cancelled = []
            for order in open_orders:
                order_id = order.get("ordId")
                if order_id:
                    await self._signed_post(
                        "/api/v5/trade/cancel-order",
                        {"instId": inst_id, "ordId": order_id},
                    )
                    cancelled.append(order_id)
            logger.info("OKX: cancelled %d orders for %s", len(cancelled), inst_id)
            return cancelled
        except Exception as e:
            logger.error("Failed to cancel orders on OKX: %s", e)
            return []

    async def close_position(self, symbol: str, side: str | None = None) -> OrderResult | None:
        position = await self.get_position(symbol)
        if not position or position.size == 0:
            logger.info("No position to close on %s", symbol)
            return None

        close_side = "sell" if position.side == "long" else "buy"
        return await self.place_market_order(symbol, close_side, position.size)

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        if self.market_type == "spot":
            return
        inst_id = self._to_inst_id(symbol)
        try:
            await self._signed_post(
                "/api/v5/account/set-leverage",
                {
                    "instId": inst_id,
                    "lever": str(leverage),
                    "mgnMode": self.td_mode,
                },
            )
            logger.info("OKX leverage set: %s -> %dx", inst_id, leverage)
        except Exception as e:
            logger.warning("Failed to set leverage on OKX: %s", e)

    async def get_ticker_price(self, symbol: str) -> float:
        inst_id = self._to_inst_id(symbol)
        url = f"{self.base_url}/api/v5/market/ticker"
        result = await self._request("GET", url, params={"instId": inst_id})
        data = result.get("data", [])
        if data:
            return float(data[0].get("last", 0))
        return 0.0
