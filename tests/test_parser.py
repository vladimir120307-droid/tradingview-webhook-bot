"""
Tests for the webhook alert parser.
Covers JSON parsing, plain-text parsing, validation, and edge cases.
"""

import pytest

from src.webhook.parser import parse_alert, AlertData, VALID_ACTIONS, VALID_EXCHANGES


class TestJSONParsing:
    """Tests for JSON alert parsing."""

    def test_basic_json_alert(self):
        payload = {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "action": "open_long",
            "secret": "test_secret",
        }
        alert = parse_alert(payload)
        assert alert.exchange == "binance"
        assert alert.symbol == "BTCUSDT"
        assert alert.action == "open_long"
        assert alert.order_type == "market"

    def test_full_json_alert(self):
        payload = {
            "exchange": "bybit",
            "symbol": "ETHUSDT",
            "action": "open_short",
            "order_type": "limit",
            "price": 3500.50,
            "size_type": "risk",
            "size_value": 1.5,
            "leverage": 10,
            "stop_loss": 3600,
            "take_profit": 3200,
            "account": "scalping",
            "comment": "ETH resistance rejection",
        }
        alert = parse_alert(payload)
        assert alert.exchange == "bybit"
        assert alert.symbol == "ETHUSDT"
        assert alert.action == "open_short"
        assert alert.order_type == "limit"
        assert alert.price == 3500.50
        assert alert.size_type == "risk"
        assert alert.size_value == 1.5
        assert alert.leverage == 10
        assert alert.stop_loss == 3600.0
        assert alert.take_profit == 3200.0
        assert alert.account == "scalping"
        assert alert.comment == "ETH resistance rejection"

    def test_symbol_normalization(self):
        payload = {
            "exchange": "okx",
            "symbol": "BTC/USDT",
            "action": "close_long",
        }
        alert = parse_alert(payload)
        assert alert.symbol == "BTCUSDT"

    def test_case_insensitive_exchange(self):
        payload = {
            "exchange": "BINANCE",
            "symbol": "BTCUSDT",
            "action": "OPEN_LONG",
        }
        alert = parse_alert(payload)
        assert alert.exchange == "binance"
        assert alert.action == "open_long"

    def test_missing_exchange_raises(self):
        with pytest.raises(ValueError, match="exchange"):
            parse_alert({"symbol": "BTCUSDT", "action": "open_long"})

    def test_missing_symbol_raises(self):
        with pytest.raises(ValueError, match="symbol"):
            parse_alert({"exchange": "binance", "action": "open_long"})

    def test_missing_action_raises(self):
        with pytest.raises(ValueError, match="action"):
            parse_alert({"exchange": "binance", "symbol": "BTCUSDT"})

    def test_invalid_exchange_raises(self):
        with pytest.raises(ValueError, match="Unsupported exchange"):
            parse_alert({
                "exchange": "kraken",
                "symbol": "BTCUSDT",
                "action": "open_long",
            })

    def test_invalid_action_raises(self):
        with pytest.raises(ValueError, match="Invalid action"):
            parse_alert({
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "action": "yolo_buy",
            })

    def test_limit_order_without_price_raises(self):
        with pytest.raises(ValueError, match="price"):
            parse_alert({
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "action": "open_long",
                "order_type": "limit",
            })

    def test_negative_size_value_raises(self):
        with pytest.raises(ValueError, match="size_value"):
            parse_alert({
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "action": "open_long",
                "size_value": -5,
            })

    def test_default_values(self):
        alert = parse_alert({
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "action": "open_long",
        })
        assert alert.order_type == "market"
        assert alert.size_type == "percent"
        assert alert.size_value == 10.0
        assert alert.leverage is None
        assert alert.stop_loss is None
        assert alert.take_profit is None
        assert alert.account is None


class TestTextParsing:
    """Tests for plain-text alert parsing."""

    def test_basic_text_alert(self):
        text = "BINANCE:BTCUSDT OPEN_LONG MARKET 25% LEV:10 SL:42000 TP:48000"
        alert = parse_alert(text)
        assert alert.exchange == "binance"
        assert alert.symbol == "BTCUSDT"
        assert alert.action == "open_long"
        assert alert.order_type == "market"
        assert alert.size_value == 25.0
        assert alert.leverage == 10
        assert alert.stop_loss == 42000.0
        assert alert.take_profit == 48000.0

    def test_minimal_text_alert(self):
        text = "BYBIT:ETHUSDT CLOSE_LONG"
        alert = parse_alert(text)
        assert alert.exchange == "bybit"
        assert alert.symbol == "ETHUSDT"
        assert alert.action == "close_long"

    def test_text_case_insensitive(self):
        text = "binance:btcusdt open_short"
        alert = parse_alert(text)
        assert alert.exchange == "binance"
        assert alert.symbol == "BTCUSDT"
        assert alert.action == "open_short"

    def test_invalid_text_raises(self):
        with pytest.raises(ValueError, match="Could not parse"):
            parse_alert("this is not a valid alert")


class TestAllActions:
    """Verify all supported actions are parseable."""

    @pytest.mark.parametrize("action", sorted(VALID_ACTIONS))
    def test_valid_action(self, action):
        payload = {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "action": action,
        }
        # Some actions need extra fields
        if action in ("set_sl",):
            payload["stop_loss"] = 40000
        if action in ("set_tp",):
            payload["take_profit"] = 50000

        alert = parse_alert(payload)
        assert alert.action == action


class TestAllExchanges:
    """Verify all supported exchanges are accepted."""

    @pytest.mark.parametrize("exchange", sorted(VALID_EXCHANGES))
    def test_valid_exchange(self, exchange):
        alert = parse_alert({
            "exchange": exchange,
            "symbol": "BTCUSDT",
            "action": "open_long",
        })
        assert alert.exchange == exchange
