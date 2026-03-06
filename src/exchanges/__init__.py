"""
Exchange client factory.
Creates and manages exchange client instances for each configured account.
"""

from src.exchanges.base import BaseExchange
from src.exchanges.binance import BinanceClient
from src.exchanges.bybit import BybitClient
from src.exchanges.okx import OKXClient

EXCHANGE_MAP = {
    "binance": BinanceClient,
    "bybit": BybitClient,
    "okx": OKXClient,
}


async def create_exchange_clients(accounts: dict) -> dict[str, BaseExchange]:
    """
    Initialize exchange client instances for all configured accounts.
    Returns a dict mapping account_name -> ExchangeClient.
    """
    clients: dict[str, BaseExchange] = {}

    for account_name, account_cfg in accounts.items():
        exchange = account_cfg.get("exchange", "").lower()
        cls = EXCHANGE_MAP.get(exchange)
        if cls is None:
            raise ValueError(f"Unsupported exchange '{exchange}' in account '{account_name}'")

        client = cls(
            api_key=account_cfg.get("api_key", ""),
            api_secret=account_cfg.get("api_secret", ""),
            passphrase=account_cfg.get("passphrase"),
            testnet=str(account_cfg.get("testnet", "false")).lower() == "true",
            market_type=account_cfg.get("market_type", "futures"),
            margin_type=account_cfg.get("margin_type", "cross"),
            default_leverage=int(account_cfg.get("default_leverage", 1)),
            rate_limit=int(account_cfg.get("rate_limit_per_second", 10)),
        )
        await client.initialize()
        clients[account_name] = client

    return clients


__all__ = [
    "BaseExchange",
    "BinanceClient",
    "BybitClient",
    "OKXClient",
    "create_exchange_clients",
]
