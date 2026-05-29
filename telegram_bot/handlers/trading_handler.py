from telegram import Update
from telegram.ext import ContextTypes

from utils.logger import get_logger

logger = get_logger(__name__)


class TradingHandler:
    """Telegram command handlers for manual trading operations."""

    def __init__(self, trading_engine) -> None:
        self._engine = trading_engine

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/positions — show all open positions."""
        portfolio = self._engine.portfolio
        positions = portfolio.get_all_positions()

        if not positions:
            await update.message.reply_text("No open positions.")
            return

        lines = ["*Open Positions*\n"]
        for code, pos in positions.items():
            sign = "+" if pos.profit_pct >= 0 else ""
            lines.append(
                f"{pos.name} ({code})\n"
                f"  Strategy: {pos.strategy_name}\n"
                f"  Qty: {pos.total_quantity:,}  Avg: {pos.average_price:,.0f}\n"
                f"  Current: {pos.current_price:,.0f}  P/L: {sign}{pos.profit_pct:.2f}%"
            )

        lines.append(
            f"\nTotal P/L: {portfolio.total_profit_loss():+,.0f} KRW "
            f"({portfolio.total_profit_pct():+.2f}%)"
        )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def cmd_sell(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/sell <code> — manually sell a specific stock."""
        if not context.args:
            await update.message.reply_text("Usage: /sell <stock_code>")
            return

        code = context.args[0].strip()
        position = self._engine.portfolio.get_position(code)
        if position is None:
            await update.message.reply_text(f"No position found for {code}.")
            return

        success = self._engine.sell_manager.execute_sell(code, reason="manual")
        if success:
            await update.message.reply_text(
                f"Sold {position.name} ({code}) — {position.total_quantity:,} shares "
                f"@ market price."
            )
        else:
            await update.message.reply_text(f"Failed to sell {code}. Check logs.")

    async def cmd_sell_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/sell_all — close all open positions."""
        positions = self._engine.portfolio.get_all_positions()
        if not positions:
            await update.message.reply_text("No positions to sell.")
            return

        sold = []
        failed = []
        for code in list(positions):
            ok = self._engine.sell_manager.execute_sell(code, reason="manual_sell_all")
            (sold if ok else failed).append(code)

        parts = []
        if sold:
            parts.append(f"Sold: {', '.join(sold)}")
        if failed:
            parts.append(f"Failed: {', '.join(failed)}")
        await update.message.reply_text("\n".join(parts) or "Done.")

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/balance — show available cash and portfolio value."""
        try:
            balance = self._engine.order_manager.get_balance()
        except Exception:
            balance = {}

        portfolio = self._engine.portfolio
        cash_str = balance.get("주문가능금액", "N/A")
        invested = portfolio.total_invested()
        value = portfolio.total_current_value()
        pnl = portfolio.total_profit_loss()
        sign = "+" if pnl >= 0 else ""

        text = (
            f"*Balance*\n"
            f"Available cash: {cash_str} KRW\n"
            f"Invested: {invested:,.0f} KRW\n"
            f"Portfolio value: {value:,.0f} KRW\n"
            f"Unrealised P/L: {sign}{pnl:,.0f} KRW ({portfolio.total_profit_pct():+.2f}%)"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
