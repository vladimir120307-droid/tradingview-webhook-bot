"""
FastAPI webhook server.
Receives TradingView alerts and dispatches them to the trade executor.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse

from src.config import get_settings
from src.utils.logger import setup_logging
from src.webhook.validator import validate_ip, validate_secret
from src.webhook.parser import parse_alert
from src.webhook.handlers import AlertHandler
from src.storage.database import Database
from src.exchanges import create_exchange_clients

logger = logging.getLogger("webhook.server")

_handler: AlertHandler | None = None
_db: Database | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global _handler, _db

    settings = get_settings()
    setup_logging(settings.logging_config)

    logger.info("Starting TradingView Webhook Bot v1.0.0")
    logger.info("Server: %s:%s", settings.server.get("host"), settings.server.get("port"))

    _db = Database(settings.database.get("path", "data/trades.db"))
    await _db.initialize()

    exchange_clients = await create_exchange_clients(settings.accounts)
    _handler = AlertHandler(
        exchange_clients=exchange_clients,
        settings=settings,
        database=_db,
    )

    logger.info("Loaded %d exchange account(s)", len(exchange_clients))
    logger.info("Webhook bot is ready to receive alerts")

    yield

    logger.info("Shutting down webhook bot...")
    for client in exchange_clients.values():
        await client.close()
    if _db:
        await _db.close()


app = FastAPI(
    title="TradingView Webhook Bot",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and Docker."""
    return {"status": "ok", "version": "1.0.0"}


@app.post("/webhook")
async def receive_webhook(request: Request):
    """
    Main webhook endpoint.
    Receives TradingView alerts, validates, parses, and executes trades.
    """
    settings = get_settings()

    # --- IP Whitelist ---
    client_ip = request.headers.get("X-Real-IP") or request.headers.get(
        "X-Forwarded-For", ""
    ).split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"

    if settings.ip_whitelist_enabled:
        if not validate_ip(client_ip, settings.tradingview_ips):
            logger.warning("Webhook rejected: IP %s not whitelisted", client_ip)
            raise HTTPException(status_code=403, detail="IP not whitelisted")

    # --- Parse body ---
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
    else:
        raw = await request.body()
        body = raw.decode("utf-8", errors="replace")

    # --- Validate secret ---
    if settings.require_secret:
        secret = body.get("secret") if isinstance(body, dict) else None
        if not validate_secret(secret, settings.webhook_secret):
            logger.warning("Webhook rejected: invalid secret from %s", client_ip)
            raise HTTPException(status_code=401, detail="Invalid secret")

    # --- Parse alert ---
    try:
        alert = parse_alert(body)
    except ValueError as e:
        logger.warning("Failed to parse alert: %s", e)
        raise HTTPException(status_code=400, detail=f"Parse error: {e}")

    logger.info(
        "Alert received: %s %s on %s (account: %s)",
        alert.action,
        alert.symbol,
        alert.exchange,
        alert.account or "default",
    )

    # --- Execute ---
    try:
        result = await _handler.handle(alert)
    except Exception as e:
        logger.exception("Error handling alert: %s", e)
        raise HTTPException(status_code=500, detail=f"Execution error: {e}")

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "action": alert.action,
            "symbol": alert.symbol,
            "exchange": alert.exchange,
            "result": result,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": str(exc)},
    )


def main():
    """Entry point for running the server."""
    settings = get_settings()
    uvicorn.run(
        "src.server:app",
        host=settings.server.get("host", "0.0.0.0"),
        port=int(settings.server.get("port", 8000)),
        workers=int(settings.server.get("workers", 1)),
        log_level=settings.server.get("log_level", "info"),
    )


if __name__ == "__main__":
    main()
