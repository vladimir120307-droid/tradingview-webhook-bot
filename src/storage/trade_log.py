"""
Trade log utilities.
Provides formatted trade history exports and performance reporting.
"""

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any

from src.storage.database import Database

logger = logging.getLogger("storage.trade_log")


class TradeLogger:
    """High-level trade logging and reporting utilities."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def get_performance_summary(self, days: int = 30) -> str:
        """Generate a human-readable performance summary."""
        stats = await self._db.get_trade_stats(days)
        if not stats or stats.get("total_trades", 0) == 0:
            return f"No closed trades in the last {days} days."

        total = stats["total_trades"]
        wins = stats["winning_trades"]
        losses = stats["losing_trades"]
        win_rate = stats["win_rate"]
        total_pnl = stats["total_pnl"]
        avg_win = stats["avg_win"]
        avg_loss = stats["avg_loss"]
        best = stats["best_trade"]
        worst = stats["worst_trade"]
        fees = stats["total_fees"]

        # Calculate profit factor
        gross_profit = wins * avg_win if avg_win else 0
        gross_loss = losses * avg_loss if avg_loss else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        # Calculate expectancy
        expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss) if avg_loss else 0

        lines = [
            f"Performance Summary ({days} days)",
            "=" * 40,
            f"Total Trades:    {total}",
            f"Win / Loss:      {wins} / {losses}",
            f"Win Rate:        {win_rate:.1f}%",
            f"",
            f"Total P&L:       ${total_pnl:+,.2f}",
            f"Total Fees:      ${fees:,.2f}",
            f"Net P&L:         ${total_pnl - fees:+,.2f}",
            f"",
            f"Avg Win:         ${avg_win:,.2f}",
            f"Avg Loss:        ${avg_loss:,.2f}",
            f"Best Trade:      ${best:+,.2f}",
            f"Worst Trade:     ${worst:+,.2f}",
            f"",
            f"Profit Factor:   {profit_factor:.2f}",
            f"Expectancy:      ${expectancy:+,.2f}",
        ]

        return "\n".join(lines)

    async def export_csv(self, limit: int = 1000) -> str:
        """Export recent trades as a CSV string."""
        trades = await self._db.get_recent_trades(limit)
        if not trades:
            return ""

        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "id", "created_at", "exchange", "symbol", "action", "side",
                "quantity", "price", "notional", "order_type", "stop_loss",
                "take_profit", "leverage", "pnl", "fees", "status",
                "order_id", "account", "comment",
            ],
        )
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade)

        return output.getvalue()

    async def get_symbol_breakdown(self, days: int = 30) -> list[dict[str, Any]]:
        """Get P&L breakdown by symbol for the given period."""
        trades = await self._db.get_recent_trades(5000)
        if not trades:
            return []

        symbol_stats: dict[str, dict[str, Any]] = {}

        for trade in trades:
            if not trade.get("action", "").startswith("close_"):
                continue

            symbol = trade.get("symbol", "unknown")
            if symbol not in symbol_stats:
                symbol_stats[symbol] = {
                    "symbol": symbol,
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "total_pnl": 0.0,
                    "total_fees": 0.0,
                }

            stats = symbol_stats[symbol]
            stats["trades"] += 1
            pnl = trade.get("pnl", 0) or 0
            stats["total_pnl"] += pnl
            stats["total_fees"] += trade.get("fees", 0) or 0

            if pnl > 0:
                stats["wins"] += 1
            elif pnl < 0:
                stats["losses"] += 1

        for stats in symbol_stats.values():
            total = stats["trades"]
            stats["win_rate"] = (stats["wins"] / total * 100) if total > 0 else 0

        return sorted(symbol_stats.values(), key=lambda x: x["total_pnl"], reverse=True)

    async def get_daily_summary(self, date_str: str | None = None) -> dict[str, Any]:
        """Get trading summary for a specific day."""
        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        pnl = await self._db.get_daily_pnl(date_str)
        trades = await self._db.get_recent_trades(1000)

        day_trades = [
            t for t in trades
            if t.get("created_at", "").startswith(date_str)
        ]

        opens = sum(1 for t in day_trades if t.get("action", "").startswith("open_"))
        closes = sum(1 for t in day_trades if t.get("action", "").startswith("close_"))

        return {
            "date": date_str,
            "total_trades": len(day_trades),
            "opens": opens,
            "closes": closes,
            "pnl": pnl,
        }
