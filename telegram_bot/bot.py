import functools
from typing import Callable, List

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from telegram_bot.handlers.status_handler import StatusHandler
from telegram_bot.handlers.strategy_handler import StrategyHandler
from telegram_bot.handlers.trading_handler import TradingHandler
from utils.logger import get_logger

logger = get_logger(__name__)


def _require_auth(user_ids: List[int]):
    """Decorator that rejects commands from users not in the allowed list."""
    def decorator(handler: Callable):
        @functools.wraps(handler)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            if user is None or user.id not in user_ids:
                logger.warning("Unauthorised access from user_id=%s", user.id if user else "?")
                await update.message.reply_text("Unauthorized.")
                return
            return await handler(update, context)
        return wrapper
    return decorator


class TradingBot:
    """Telegram bot that exposes trading controls."""

    def __init__(
        self,
        token: str,
        allowed_users: List[int],
        trading_engine,
    ) -> None:
        self._token = token
        self._allowed_users = allowed_users
        self._engine = trading_engine
        self._app: Application = None

        self._status_handler = StatusHandler(trading_engine)
        self._strategy_handler = StrategyHandler(trading_engine)
        self._trading_handler = TradingHandler(trading_engine)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def build(self) -> None:
        self._app = Application.builder().token(self._token).build()
        self._register_handlers()
        logger.info("Telegram bot application built.")

    def _register_handlers(self) -> None:
        auth = _require_auth(self._allowed_users)
        app = self._app

        app.add_handler(CommandHandler("start", self._status_handler.cmd_start))
        app.add_handler(CommandHandler("help", self._status_handler.cmd_help))
        app.add_handler(CommandHandler("status", auth(self._status_handler.cmd_status)))

        app.add_handler(CommandHandler("strategies", auth(self._strategy_handler.cmd_strategies)))
        app.add_handler(CommandHandler("enable", auth(self._strategy_handler.cmd_enable)))
        app.add_handler(CommandHandler("disable", auth(self._strategy_handler.cmd_disable)))
        app.add_handler(CommandHandler("strategy_status", auth(self._strategy_handler.cmd_strategy_status)))

        app.add_handler(CommandHandler("positions", auth(self._trading_handler.cmd_positions)))
        app.add_handler(CommandHandler("sell", auth(self._trading_handler.cmd_sell)))
        app.add_handler(CommandHandler("sell_all", auth(self._trading_handler.cmd_sell_all)))
        app.add_handler(CommandHandler("balance", auth(self._trading_handler.cmd_balance)))

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run_polling(self) -> None:
        """Start the bot in blocking polling mode (for use outside PyQt loop)."""
        if self._app is None:
            self.build()
        logger.info("Starting Telegram bot polling...")
        self._app.run_polling(drop_pending_updates=True)

    async def send_message(self, user_id: int, text: str) -> None:
        """Send a proactive message to a specific user."""
        if self._app is None:
            return
        try:
            await self._app.bot.send_message(chat_id=user_id, text=text)
        except Exception:
            logger.exception("Failed to send message to user_id=%d", user_id)

    async def broadcast(self, text: str) -> None:
        """Send a message to all allowed users."""
        for uid in self._allowed_users:
            await self.send_message(uid, text)

    def get_application(self) -> Application:
        if self._app is None:
            self.build()
        return self._app
