from core.kiwoom.order import OrderManager
from core.strategy.manager import StrategyManager
from core.trading.portfolio import Portfolio, Position
from utils.logger import get_logger

logger = get_logger(__name__)


class SellManager:
    """Monitors open positions and triggers automatic sell orders."""

    def __init__(
        self,
        order_manager: OrderManager,
        portfolio: Portfolio,
        strategy_manager: StrategyManager,
    ) -> None:
        self._orders = order_manager
        self._portfolio = portfolio
        self._strategy_manager = strategy_manager

    # ------------------------------------------------------------------
    # Periodic check (called every ~60 seconds from main loop)
    # ------------------------------------------------------------------

    def check_and_sell_all(self) -> None:
        """Iterate all positions and sell those that meet exit criteria."""
        for code, position in list(self._portfolio.get_all_positions().items()):
            try:
                self._check_position(position)
            except Exception:
                logger.exception("Error checking sell conditions for code=%s", code)

    # ------------------------------------------------------------------
    # Per-position evaluation
    # ------------------------------------------------------------------

    def _check_position(self, position: Position) -> None:
        strategy = self._strategy_manager.get_strategy(position.strategy_name)
        if strategy is None:
            logger.warning(
                "Strategy '%s' not found for position code=%s",
                position.strategy_name, position.code,
            )
            return

        should_sell, reason = strategy.should_sell(position, position.current_price)
        if should_sell:
            self.execute_sell(position.code, reason)

    # ------------------------------------------------------------------
    # Realtime price update (called from RealtimeManager callback)
    # ------------------------------------------------------------------

    def on_price_update(self, code: str, current_price: float) -> None:
        """Update position price and check sell conditions immediately."""
        position = self._portfolio.update_position(code, current_price)
        if position is None:
            return
        try:
            self._check_position(position)
        except Exception:
            logger.exception("Error on price update sell check for code=%s", code)

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    def execute_sell(self, code: str, reason: str = "") -> bool:
        """Place a market sell for the full position and remove it from portfolio."""
        position = self._portfolio.get_position(code)
        if position is None:
            logger.warning("Cannot sell code=%s: position not found.", code)
            return False

        qty = position.total_quantity
        result = self._orders.sell_market(code, qty)
        if result < 0:
            logger.error(
                "sell_market failed for code=%s qty=%d result=%d", code, qty, result
            )
            return False

        self._portfolio.remove_position(code)
        logger.info(
            "Sold code=%s qty=%d reason='%s' profit=%.2f%%",
            code, qty, reason, position.profit_pct,
        )
        return True
