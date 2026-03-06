"""
Configuration loader.
Merges settings.yaml, exchanges.yaml, and environment variables.
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ${ENV_VAR} placeholders in config values."""
    if isinstance(value, str):
        def _replacer(match: re.Match) -> str:
            var_name = match.group(1)
            env_val = os.getenv(var_name, "")
            return env_val
        return _ENV_VAR_PATTERN.sub(_replacer, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def _load_yaml(path: Path) -> dict:
    """Load a YAML file and resolve environment variable placeholders."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return _resolve_env_vars(raw)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dicts; override values win."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class Settings:
    """Application settings singleton."""

    _instance: "Settings | None" = None

    def __new__(cls) -> "Settings":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self) -> None:
        if self._loaded:
            return
        self._settings = _load_yaml(CONFIG_DIR / "settings.yaml")
        self._exchanges = _load_yaml(CONFIG_DIR / "exchanges.yaml")
        self._apply_env_overrides()
        self._loaded = True

    def _apply_env_overrides(self) -> None:
        """Override settings with environment variables where applicable."""
        env_map = {
            "SERVER_HOST": ("server", "host"),
            "SERVER_PORT": ("server", "port"),
            "WEBHOOK_SECRET": ("webhook", "secret"),
        }
        for env_var, path in env_map.items():
            value = os.getenv(env_var)
            if value is not None:
                section = self._settings
                for key in path[:-1]:
                    section = section.setdefault(key, {})
                final_key = path[-1]
                try:
                    section[final_key] = int(value)
                except (ValueError, TypeError):
                    section[final_key] = value

    @property
    def server(self) -> dict:
        return self._settings.get("server", {})

    @property
    def webhook(self) -> dict:
        return self._settings.get("webhook", {})

    @property
    def risk(self) -> dict:
        return self._settings.get("risk", {})

    @property
    def trading(self) -> dict:
        return self._settings.get("trading", {})

    @property
    def notifications(self) -> dict:
        return self._settings.get("notifications", {})

    @property
    def logging_config(self) -> dict:
        return self._settings.get("logging", {})

    @property
    def database(self) -> dict:
        return self._settings.get("database", {})

    @property
    def accounts(self) -> dict:
        return self._exchanges.get("accounts", {})

    def get_account(self, account_name: str | None, exchange: str | None = None) -> dict:
        """
        Retrieve account config by name. If account_name is None,
        return the first account matching the given exchange.
        """
        accounts = self.accounts
        if account_name and account_name in accounts:
            return accounts[account_name]

        if exchange:
            for name, acct in accounts.items():
                if acct.get("exchange", "").lower() == exchange.lower():
                    return acct

        if accounts:
            return next(iter(accounts.values()))

        raise ValueError(f"No account found for account={account_name}, exchange={exchange}")

    @property
    def webhook_secret(self) -> str | None:
        return self.webhook.get("secret") or os.getenv("WEBHOOK_SECRET")

    @property
    def tradingview_ips(self) -> list[str]:
        return self.webhook.get("tradingview_ips", [])

    @property
    def ip_whitelist_enabled(self) -> bool:
        return self.webhook.get("ip_whitelist_enabled", True)

    @property
    def require_secret(self) -> bool:
        return self.webhook.get("require_secret", True)

    def reload(self) -> None:
        """Force-reload all configuration files."""
        self._loaded = False
        self._settings = _load_yaml(CONFIG_DIR / "settings.yaml")
        self._exchanges = _load_yaml(CONFIG_DIR / "exchanges.yaml")
        self._apply_env_overrides()
        self._loaded = True


def get_settings() -> Settings:
    """Return the global Settings instance."""
    return Settings()
