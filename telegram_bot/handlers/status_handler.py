import asyncio
from datetime import datetime
from typing import List

from telegram import Update
from telegram.ext import ContextTypes

from utils.logger import get_logger

logger = get_logger(__name__)

HELP_TEXT = """
*Available Commands*

*Status*
/start — Welcome message and command overview
/status — Current system state (strategies, positions, P/L)
/help — This help message

*Strategies*
/strategies — List all strategies with enabled/disabled state
/enable <name> — Activate a strategy
/disable <name> — Deactivate a strategy
/strategy\\_status — Detailed configuration of all strategies

*Trading*
/positions — Open positions with P/L and strategy info
/sell <code> — Manually sell a specific stock (market order)
/sell\\_all — Liquidate all open positions
/balance — Available cash and total portfolio value
""".strip()


class StatusHandler:
    """Handles /start, /status, /help commands and periodic status broadcasts."""

    def __init__(self, trading_engine) -> None:
        self._engine = trading_engine

    # ------------------------------------------------------------------
    # /start
    # ------------------------------------------------------------------

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        welcome = (
            f"Welcome, {user.first_name if user else 'trader'}!\n\n"
            "This bot controls your Kiwoom automated trading system.\n\n"
            + HELP_TEXT
        )
        await update.message.reply_text(welcome, parse_mode="Markdown")

    # ------------------------------------------------------------------
    # /help
    # ------------------------------------------------------------------

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

    # ------------------------------------------------------------------
    # /status
    # ------------------------------------------------------------------

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = self._build_status_text()
        await update.message.reply_text(text, parse_mode="Markdown")

    def _build_status_text(self) -> str:
        try:
            strategy_manager = self._engine.strategy_manager
            portfolio = self._engine.portfolio

            enabled = strategy_manager.get_enabled_strategies()
            all_strategies = strategy_manager.get_all_strategies()

            lines = [
                f"*System Status* — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                f"*Strategies:* {len(enabled)}/{len(all_strategies)} active",
            ]

            for name, strategy in all_strategies.items():
                state = "ON" if strategy.is_enabled else "OFF"
                lines.append(f"  • {name}: {state}")

            positions = portfolio.get_all_positions()
            lines += [
                "",
                f"*Open Positions:* {len(positions)}",
            ]

            if positions:
                total_pnl = portfolio.total_profit_loss()
                total_pct = portfolio.total_profit_pct()
                lines.append(f"*Total P/L:* {total_pnl:+,.0f} KRW ({total_pct:+.2f}%)")

            return "\n".join(lines)

        except Exception:
            logger.exception("Failed to build status text.")
            return "Error retrieving system status."

    # ------------------------------------------------------------------
    # Periodic broadcast (called from external scheduler)
    # ------------------------------------------------------------------

    async def periodic_status_report(self, bot, user_ids: List[int]) -> None:
        """Send a status report to all allowed users every 5 minutes."""
        text = self._build_status_text()
        for uid in user_ids:
            try:
                await bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
            except Exception:
                logger.exception("Failed to send periodic status to user_id=%d", uid)

    def schedule_periodic_report(self, application, user_ids: List[int], interval_seconds: int = 300) -> None:
        """Register a repeating job with the PTB JobQueue (if available)."""
        job_queue = getattr(application, "job_queue", None)
        if job_queue is None:
            logger.warning("JobQueue not available; periodic reports disabled.")
            return

        async def _job(context: ContextTypes.DEFAULT_TYPE) -> None:
            text = self._build_status_text()
            for uid in user_ids:
                try:
                    await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
                except Exception:
                    logger.exception("Failed to send scheduled status to user_id=%d", uid)

        job_queue.run_repeating(_job, interval=interval_seconds, first=interval_seconds)
        logger.info("Periodic status report scheduled every %ds.", interval_seconds)
