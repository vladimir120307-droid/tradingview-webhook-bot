"""
SQLite database for trade logging and position tracking.
Uses aiosqlite for async operations.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger("storage.database")

CREATE_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    side TEXT,
    quantity REAL DEFAULT 0,
    price REAL DEFAULT 0,
    notional REAL DEFAULT 0,
    order_type TEXT,
    stop_loss REAL,
    take_profit REAL,
    leverage INTEGER DEFAULT 1,
    pnl REAL DEFAULT 0,
    fees REAL DEFAULT 0,
    status TEXT DEFAULT 'executed',
    order_id TEXT,
    account TEXT,
    comment TEXT
);
"""

CREATE_POSITIONS_TABLE = """
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    size REAL NOT NULL DEFAULT 0,
    entry_price REAL DEFAULT 0,
    leverage INTEGER DEFAULT 1,
    account TEXT,
    is_open INTEGER DEFAULT 1
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at);
CREATE INDEX IF NOT EXISTS idx_trades_exchange ON trades(exchange);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_open ON positions(is_open);
"""


class Database:
    """Async SQLite database for trade logging and position tracking."""

    def __init__(self, db_path: str = "data/trades.db") -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create the database and tables if they don't exist."""
        db_dir = Path(self._db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row

        await self._conn.executescript(CREATE_TRADES_TABLE)
        await self._conn.executescript(CREATE_POSITIONS_TABLE)
        await self._conn.executescript(CREATE_INDEXES)
        await self._conn.commit()

        logger.info("Database initialized at %s", self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def log_trade(
        self,
        exchange: str,
        symbol: str,
        action: str,
        side: str = "",
        quantity: float = 0,
        price: float = 0,
        order_type: str = "market",
        stop_loss: float | None = None,
        take_profit: float | None = None,
        leverage: int | None = None,
        account: str | None = None,
        order_id: str = "",
        comment: str | None = None,
        pnl: float = 0,
        fees: float = 0,
    ) -> int:
        """
        Log a trade to the database.
        Returns the trade ID.
        """
        if not self._conn:
            raise RuntimeError("Database not initialized")

        notional = quantity * price if price else 0

        cursor = await self._conn.execute(
            """
            INSERT INTO trades
                (exchange, symbol, action, side, quantity, price, notional,
                 order_type, stop_loss, take_profit, leverage, pnl, fees,
                 order_id, account, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exchange, symbol, action, side, quantity, price, notional,
                order_type, stop_loss, take_profit, leverage or 1,
                pnl, fees, order_id, account, comment,
            ),
        )
        await self._conn.commit()

        trade_id = cursor.lastrowid or 0
        logger.debug("Trade logged: id=%d %s %s %s", trade_id, action, symbol, exchange)

        # Update position tracking
        await self._update_position(exchange, symbol, action, side, quantity, price, leverage, account)

        return trade_id

    async def _update_position(
        self, exchange: str, symbol: str, action: str, side: str,
        quantity: float, price: float, leverage: int | None, account: str | None,
    ) -> None:
        """Update the positions table based on trade action."""
        if not self._conn:
            return

        if action.startswith("open_") or action == "scale_in":
            # Check for existing position
            row = await self._conn.execute_fetchall(
                "SELECT id, size FROM positions WHERE symbol = ? AND exchange = ? AND is_open = 1",
                (symbol, exchange),
            )
            if row:
                # Update existing position
                new_size = row[0][1] + quantity
                await self._conn.execute(
                    "UPDATE positions SET size = ?, updated_at = datetime('now') WHERE id = ?",
                    (new_size, row[0][0]),
                )
            else:
                # Insert new position
                pos_side = "long" if "long" in action or side.upper() == "BUY" else "short"
                await self._conn.execute(
                    """
                    INSERT INTO positions (exchange, symbol, side, size, entry_price, leverage, account)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (exchange, symbol, pos_side, quantity, price, leverage or 1, account),
                )

        elif action.startswith("close_") or action == "close_all":
            await self._conn.execute(
                "UPDATE positions SET is_open = 0, updated_at = datetime('now') WHERE symbol = ? AND exchange = ? AND is_open = 1",
                (symbol, exchange),
            )

        elif action == "scale_out":
            row = await self._conn.execute_fetchall(
                "SELECT id, size FROM positions WHERE symbol = ? AND exchange = ? AND is_open = 1",
                (symbol, exchange),
            )
            if row:
                new_size = max(0, row[0][1] - quantity)
                if new_size <= 0:
                    await self._conn.execute(
                        "UPDATE positions SET is_open = 0, updated_at = datetime('now') WHERE id = ?",
                        (row[0][0],),
                    )
                else:
                    await self._conn.execute(
                        "UPDATE positions SET size = ?, updated_at = datetime('now') WHERE id = ?",
                        (new_size, row[0][0]),
                    )

        await self._conn.commit()

    async def get_daily_pnl(self, date_str: str) -> float:
        """Get the total realized P&L for a specific date."""
        if not self._conn:
            return 0.0

        rows = await self._conn.execute_fetchall(
            "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE DATE(created_at) = ?",
            (date_str,),
        )
        return float(rows[0][0]) if rows else 0.0

    async def count_open_positions(self) -> int:
        """Count the total number of open positions."""
        if not self._conn:
            return 0

        rows = await self._conn.execute_fetchall(
            "SELECT COUNT(*) FROM positions WHERE is_open = 1"
        )
        return int(rows[0][0]) if rows else 0

    async def count_symbol_positions(self, symbol: str) -> int:
        """Count open positions for a specific symbol."""
        if not self._conn:
            return 0

        rows = await self._conn.execute_fetchall(
            "SELECT COUNT(*) FROM positions WHERE symbol = ? AND is_open = 1",
            (symbol,),
        )
        return int(rows[0][0]) if rows else 0

    async def get_recent_trades(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get the most recent trades."""
        if not self._conn:
            return []

        rows = await self._conn.execute_fetchall(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in rows]

    async def get_trade_stats(self, days: int = 30) -> dict[str, Any]:
        """Calculate trading statistics for the given period."""
        if not self._conn:
            return {}

        rows = await self._conn.execute_fetchall(
            """
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(pnl) as total_pnl,
                AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
                AVG(CASE WHEN pnl < 0 THEN ABS(pnl) END) as avg_loss,
                MAX(pnl) as best_trade,
                MIN(pnl) as worst_trade,
                SUM(fees) as total_fees
            FROM trades
            WHERE created_at >= datetime('now', ? || ' days')
              AND action LIKE 'close_%'
            """,
            (f"-{days}",),
        )

        if not rows:
            return {}

        row = rows[0]
        total = row[0] or 0
        wins = row[1] or 0

        return {
            "total_trades": total,
            "winning_trades": wins,
            "losing_trades": row[2] or 0,
            "win_rate": (wins / total * 100) if total > 0 else 0,
            "total_pnl": row[3] or 0,
            "avg_win": row[4] or 0,
            "avg_loss": row[5] or 0,
            "best_trade": row[6] or 0,
            "worst_trade": row[7] or 0,
            "total_fees": row[8] or 0,
        }
