"""
Tests for risk management and position sizing.
"""

import pytest

from src.trading.position_sizer import PositionSizer
from src.webhook.validator import validate_ip, validate_secret, generate_hmac_signature, validate_hmac_signature


class TestPositionSizer:
    """Tests for position sizing calculations."""

    @pytest.fixture
    def sizer(self):
        return PositionSizer({
            "min_order_value": 10.0,
            "max_single_trade_percent": 50.0,
        })

    def test_fixed_size(self, sizer):
        qty = sizer.calculate(
            balance=10000,
            current_price=50000,
            size_type="fixed",
            size_value=1000,
        )
        # 1000 USDT / 50000 price = 0.02 BTC * 1x leverage
        assert qty == pytest.approx(0.02, abs=0.001)

    def test_percent_size(self, sizer):
        qty = sizer.calculate(
            balance=10000,
            current_price=50000,
            size_type="percent",
            size_value=10.0,
        )
        # 10% of 10000 = 1000 USDT / 50000 = 0.02 BTC
        assert qty == pytest.approx(0.02, abs=0.001)

    def test_percent_size_with_leverage(self, sizer):
        qty = sizer.calculate(
            balance=10000,
            current_price=50000,
            size_type="percent",
            size_value=10.0,
            leverage=5,
        )
        # (10% of 10000) / 50000 * 5 = 0.1 BTC
        assert qty == pytest.approx(0.1, abs=0.001)

    def test_risk_based_size(self, sizer):
        qty = sizer.calculate(
            balance=10000,
            current_price=50000,
            size_type="risk",
            size_value=1.0,  # Risk 1%
            stop_loss=49000,
        )
        # risk_amount = 10000 * 0.01 = 100
        # price_distance = |50000 - 49000| = 1000
        # qty = 100 / 1000 = 0.1 BTC (before leverage)
        assert qty == pytest.approx(0.1, abs=0.01)

    def test_risk_based_without_sl_fallback(self, sizer):
        qty = sizer.calculate(
            balance=10000,
            current_price=50000,
            size_type="risk",
            size_value=1.0,
            stop_loss=None,
        )
        # Falls back to 1% of balance
        assert qty > 0

    def test_kelly_size(self, sizer):
        qty = sizer.calculate(
            balance=10000,
            current_price=50000,
            size_type="kelly",
            size_value=0.5,  # Half Kelly
            win_rate=0.60,
            avg_win=200.0,
            avg_loss=100.0,
        )
        assert qty > 0

    def test_zero_balance_returns_zero(self, sizer):
        qty = sizer.calculate(
            balance=0,
            current_price=50000,
            size_type="percent",
            size_value=10.0,
        )
        assert qty == 0.0

    def test_zero_price_returns_zero(self, sizer):
        qty = sizer.calculate(
            balance=10000,
            current_price=0,
            size_type="percent",
            size_value=10.0,
        )
        assert qty == 0.0

    def test_min_order_value_enforcement(self, sizer):
        qty = sizer.calculate(
            balance=10000,
            current_price=50000,
            size_type="fixed",
            size_value=1.0,  # $1 — below min $10
        )
        # Should be bumped to at least min_order_value / price
        notional = qty * 50000
        assert notional >= 10.0

    def test_percent_capped_at_100(self, sizer):
        qty = sizer.calculate(
            balance=10000,
            current_price=50000,
            size_type="percent",
            size_value=150.0,  # Over 100%
        )
        # Should use 100% max
        max_qty = 10000 / 50000
        assert qty <= max_qty * 1.1  # Small tolerance


class TestIPValidation:
    """Tests for IP address whitelist validation."""

    def test_tradingview_ip_allowed(self):
        assert validate_ip("52.89.214.238") is True

    def test_local_ip_allowed(self):
        assert validate_ip("127.0.0.1") is True

    def test_private_ip_allowed(self):
        assert validate_ip("192.168.1.100") is True

    def test_unknown_ip_blocked(self):
        assert validate_ip("8.8.8.8") is False

    def test_empty_ip_blocked(self):
        assert validate_ip("") is False

    def test_unknown_string_blocked(self):
        assert validate_ip("unknown") is False

    def test_invalid_ip_format_blocked(self):
        assert validate_ip("not.an.ip.address") is False

    def test_custom_whitelist(self):
        assert validate_ip("1.2.3.4", ["1.2.3.4", "5.6.7.8"]) is True
        assert validate_ip("9.9.9.9", ["1.2.3.4", "5.6.7.8"]) is False


class TestSecretValidation:
    """Tests for webhook secret validation."""

    def test_matching_secrets(self):
        assert validate_secret("my_secret", "my_secret") is True

    def test_mismatching_secrets(self):
        assert validate_secret("wrong", "correct") is False

    def test_no_expected_secret(self):
        # When no secret is configured, validation passes
        assert validate_secret(None, None) is True
        assert validate_secret(None, "") is True

    def test_no_provided_secret(self):
        assert validate_secret(None, "expected") is False
        assert validate_secret("", "expected") is False


class TestHMACSignature:
    """Tests for HMAC signature generation and validation."""

    def test_generate_and_validate(self):
        payload = '{"action":"open_long","symbol":"BTCUSDT"}'
        secret = "test_key_123"
        signature = generate_hmac_signature(payload, secret)
        assert validate_hmac_signature(payload, signature, secret) is True

    def test_invalid_signature(self):
        payload = '{"action":"open_long"}'
        secret = "test_key"
        signature = generate_hmac_signature(payload, secret)
        assert validate_hmac_signature(payload, "invalid_sig", secret) is False

    def test_tampered_payload(self):
        payload = '{"action":"open_long"}'
        secret = "test_key"
        signature = generate_hmac_signature(payload, secret)
        tampered = '{"action":"open_short"}'
        assert validate_hmac_signature(tampered, signature, secret) is False
