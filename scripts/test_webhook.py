#!/usr/bin/env python3
"""
Test webhook script.
Sends sample webhook payloads to the local server for testing.

Usage:
    python scripts/test_webhook.py
    python scripts/test_webhook.py --url http://your-server:8000/webhook
    python scripts/test_webhook.py --action open_short --symbol ETHUSDT
"""

import argparse
import json
import sys
import os

import httpx

# Default test payload
DEFAULT_PAYLOAD = {
    "secret": os.getenv("WEBHOOK_SECRET", "test_secret"),
    "exchange": "binance",
    "symbol": "BTCUSDT",
    "action": "open_long",
    "order_type": "market",
    "size_type": "percent",
    "size_value": 10,
    "leverage": 5,
    "stop_loss": 42000,
    "take_profit": 48000,
    "account": "main",
    "comment": "Test webhook from scripts/test_webhook.py",
}

TEST_SCENARIOS = {
    "open_long": {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "action": "open_long",
        "size_type": "percent",
        "size_value": 10,
        "leverage": 5,
        "stop_loss": 42000,
        "take_profit": 48000,
    },
    "open_short": {
        "exchange": "binance",
        "symbol": "ETHUSDT",
        "action": "open_short",
        "size_type": "risk",
        "size_value": 1.5,
        "leverage": 10,
        "stop_loss": 3800,
        "take_profit": 3200,
    },
    "close_long": {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "action": "close_long",
    },
    "close_all": {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "action": "close_all",
    },
    "scale_out": {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "action": "scale_out",
        "size_value": 50,
    },
}


def send_webhook(url: str, payload: dict) -> None:
    """Send a webhook payload and print the response."""
    print(f"\nSending webhook to: {url}")
    print(f"Payload:\n{json.dumps(payload, indent=2)}")
    print("-" * 50)

    try:
        response = httpx.post(
            url,
            json=payload,
            timeout=10.0,
            headers={"Content-Type": "application/json"},
        )
        print(f"Status: {response.status_code}")
        try:
            data = response.json()
            print(f"Response:\n{json.dumps(data, indent=2)}")
        except Exception:
            print(f"Response: {response.text}")

        if response.status_code == 200:
            print("\nWebhook processed successfully!")
        else:
            print(f"\nWebhook returned error: {response.status_code}")

    except httpx.ConnectError:
        print(f"\nCould not connect to {url}")
        print("Make sure the webhook server is running:")
        print("  python -m src.server")
    except Exception as e:
        print(f"\nError: {e}")


def send_text_webhook(url: str, text: str) -> None:
    """Send a plain-text webhook payload."""
    print(f"\nSending text webhook to: {url}")
    print(f"Payload: {text}")
    print("-" * 50)

    try:
        response = httpx.post(
            url,
            content=text.encode(),
            timeout=10.0,
            headers={"Content-Type": "text/plain"},
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Test TradingView webhook locally")
    parser.add_argument("--url", default="http://127.0.0.1:8000/webhook", help="Webhook URL")
    parser.add_argument("--action", default="open_long", help="Trade action to test")
    parser.add_argument("--symbol", default=None, help="Trading symbol")
    parser.add_argument("--exchange", default=None, help="Exchange name")
    parser.add_argument("--scenario", choices=TEST_SCENARIOS.keys(), help="Run a predefined scenario")
    parser.add_argument("--text", action="store_true", help="Send as plain text")
    parser.add_argument("--all", action="store_true", help="Run all test scenarios")
    args = parser.parse_args()

    if args.all:
        print("Running all test scenarios...")
        for name, scenario in TEST_SCENARIOS.items():
            payload = {**scenario, "secret": os.getenv("WEBHOOK_SECRET", "test_secret")}
            print(f"\n{'='*50}")
            print(f"Scenario: {name}")
            send_webhook(args.url, payload)
        return

    if args.scenario:
        payload = {
            **TEST_SCENARIOS[args.scenario],
            "secret": os.getenv("WEBHOOK_SECRET", "test_secret"),
        }
    else:
        payload = DEFAULT_PAYLOAD.copy()
        payload["action"] = args.action
        if args.symbol:
            payload["symbol"] = args.symbol
        if args.exchange:
            payload["exchange"] = args.exchange

    if args.text:
        text = f"{payload['exchange'].upper()}:{payload['symbol']} {payload['action'].upper()}"
        send_text_webhook(args.url, text)
    else:
        send_webhook(args.url, payload)


if __name__ == "__main__":
    main()
