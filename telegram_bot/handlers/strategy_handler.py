from telegram import Update
from telegram.ext import ContextTypes

from utils.logger import get_logger

logger = get_logger(__name__)


class StrategyHandler:
    """Telegram command handlers for strategy management."""

    def __init__(self, trading_engine) -> None:
        self._engine = trading_engine

    async def cmd_strategies(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List all strategies with their enabled/disabled status."""
        manager = self._engine.strategy_manager
        strategies = manager.get_all_strategies()

        if not strategies:
            await update.message.reply_text("No strategies loaded.")
            return

        lines = ["*Strategies*\n"]
        for name, strategy in strategies.items():
            status = "ON" if strategy.is_enabled else "OFF"
            condition = strategy.config.condition_name
            lines.append(f"[{status}] {name}\n  Condition: {condition}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def cmd_enable(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/enable <strategy_name> — activate a strategy."""
        if not context.args:
            await update.message.reply_text("Usage: /enable <strategy name>")
            return

        name = " ".join(context.args)
        success = self._engine.strategy_manager.enable_strategy(name)
        if success:
            await self._engine.on_strategy_enabled(name)
            await update.message.reply_text(f"Strategy '{name}' enabled.")
        else:
            await update.message.reply_text(f"Strategy '{name}' not found.")

    async def cmd_disable(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/disable <strategy_name> — deactivate a strategy."""
        if not context.args:
            await update.message.reply_text("Usage: /disable <strategy name>")
            return

        name = " ".join(context.args)
        success = self._engine.strategy_manager.disable_strategy(name)
        if success:
            await self._engine.on_strategy_disabled(name)
            await update.message.reply_text(f"Strategy '{name}' disabled.")
        else:
            await update.message.reply_text(f"Strategy '{name}' not found.")

    async def cmd_strategy_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/strategy_status — show detailed config for all strategies."""
        manager = self._engine.strategy_manager
        strategies = manager.get_all_strategies()

        if not strategies:
            await update.message.reply_text("No strategies loaded.")
            return

        parts = []
        for name, strategy in strategies.items():
            cfg = strategy.config
            sell = cfg.sell
            splits = "\n".join(
                f"    Step {s.step}: ratio={s.ratio:.0%}, drop={s.drop_pct:.1f}%"
                for s in cfg.buy_splits
            )
            block = (
                f"*{name}* ({'ON' if strategy.is_enabled else 'OFF'})\n"
                f"  Condition: {cfg.condition_name}\n"
                f"  Split buy:\n{splits}\n"
                f"  Stop loss: {sell.stop_loss_pct:.1f}%\n"
                f"  Trailing stop: {sell.trailing_stop_pct:.1f}% "
                f"(activates at +{sell.trailing_activate_pct:.1f}%)"
            )
            parts.append(block)

        await update.message.reply_text("\n\n".join(parts), parse_mode="Markdown")
