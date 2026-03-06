"""
Webhook request validation.
IP whitelisting and HMAC secret verification for TradingView webhooks.
"""

import hashlib
import hmac
import ipaddress
import logging
from typing import Sequence

logger = logging.getLogger("webhook.validator")

# TradingView's known webhook source IPs (updated regularly)
DEFAULT_TRADINGVIEW_IPS = [
    "52.89.214.238",
    "34.212.75.30",
    "54.218.53.128",
    "52.32.178.7",
]

# Private/local IP ranges allowed for development and testing
_LOCAL_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
]


def validate_ip(client_ip: str, whitelist: Sequence[str] | None = None) -> bool:
    """
    Validate that the request IP is from TradingView or a local network.

    Args:
        client_ip: The client's IP address string.
        whitelist: List of whitelisted IP addresses. Falls back to defaults.

    Returns:
        True if the IP is allowed, False otherwise.
    """
    if not client_ip or client_ip == "unknown":
        logger.warning("Cannot validate unknown IP")
        return False

    try:
        addr = ipaddress.ip_address(client_ip.strip())
    except ValueError:
        logger.warning("Invalid IP address format: %s", client_ip)
        return False

    # Always allow local/private IPs for development
    for network in _LOCAL_NETWORKS:
        if addr in network:
            logger.debug("IP %s is local — allowed", client_ip)
            return True

    # Check against TradingView whitelist
    allowed_ips = whitelist or DEFAULT_TRADINGVIEW_IPS
    for allowed in allowed_ips:
        try:
            if addr == ipaddress.ip_address(allowed.strip()):
                logger.debug("IP %s is whitelisted", client_ip)
                return True
        except ValueError:
            continue

    logger.warning("IP %s is not whitelisted", client_ip)
    return False


def validate_secret(provided_secret: str | None, expected_secret: str | None) -> bool:
    """
    Validate the webhook secret using constant-time comparison.

    Args:
        provided_secret: The secret from the webhook payload.
        expected_secret: The expected secret from configuration.

    Returns:
        True if secrets match, or if no secret is configured.
    """
    if not expected_secret:
        # No secret configured — skip validation
        return True

    if not provided_secret:
        logger.warning("No secret provided in webhook payload")
        return False

    is_valid = hmac.compare_digest(
        provided_secret.encode("utf-8"),
        expected_secret.encode("utf-8"),
    )

    if not is_valid:
        logger.warning("Invalid webhook secret provided")

    return is_valid


def generate_hmac_signature(payload: str, secret: str) -> str:
    """
    Generate HMAC-SHA256 signature for a payload.
    Useful for testing and verifying webhook authenticity.

    Args:
        payload: The raw payload string.
        secret: The HMAC secret key.

    Returns:
        Hex-encoded HMAC-SHA256 signature.
    """
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def validate_hmac_signature(
    payload: str, signature: str, secret: str
) -> bool:
    """
    Validate an HMAC-SHA256 signature against a payload.

    Args:
        payload: The raw payload string.
        signature: The provided signature to verify.
        secret: The HMAC secret key.

    Returns:
        True if the signature is valid.
    """
    expected = generate_hmac_signature(payload, secret)
    return hmac.compare_digest(signature, expected)
