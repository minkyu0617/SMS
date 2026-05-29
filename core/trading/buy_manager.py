from typing import Optional

from core.kiwoom.order import OrderManager
from core.strategy.base import BaseStrategy, SplitBuyConfig
from core.trading.portfolio import Portfolio, Position
from utils.logger import get_logger

logger = get_logger(__name__)


class BuyManager:
    """Executes split-buy logic for incoming condition search signals."""

    def __init__(
        self,
        order_manager: OrderManager,
        portfolio: Portfolio,
        total_investment: float,
        max_stocks: int,
    ) -> None:
        self._orders = order_manager
        self._portfolio = portfolio
        self._total_investment = total_investment
        self._max_stocks = max_stocks

    # ------------------------------------------------------------------
    # Entry point: called when a stock enters a condition
    # ------------------------------------------------------------------

    def process_candidate(
        self,
        code: str,
        name: str,
        strategy: BaseStrategy,
        current_price: float,
        stock_info: dict,
    ) -> bool:
        """Evaluate and possibly execute a buy for a condition-matched stock.

        Returns True when an order was placed.
        """
        if not strategy.is_enabled:
            return False

        if self._portfolio.has_position(code):
            return self.check_additional_buy(code, strategy, current_price)

        if self._portfolio.position_count() >= self._max_stocks:
            logger.debug(
                "Max stocks (%d) reached; skipping code=%s", self._max_stocks, code
            )
            return False

        if not strategy.should_buy(code, current_price, stock_info):
            return False

        first_split = strategy.config.buy_splits[0] if strategy.config.buy_splits else None
        if first_split is None:
            return False

        return self._execute_buy(code, name, strategy, first_split, current_price)

    # ------------------------------------------------------------------
    # Additional split-buy
    # ------------------------------------------------------------------

    def check_additional_buy(
        self,
        code: str,
        strategy: BaseStrategy,
        current_price: float,
    ) -> bool:
        """Check whether the next split-buy step should trigger for an existing position."""
        position = self._portfolio.get_position(code)
        if position is None:
            return False

        next_step = strategy.get_next_buy_step(position)
        if next_step is None:
            return False

        if next_step.drop_pct >= 0.0:
            return False

        drop_from_avg = (current_price - position.average_price) / position.average_price * 100.0
        if drop_from_avg > next_step.drop_pct:
            return False

        return self._execute_buy(
            code, position.name, strategy, next_step, current_price, existing=True
        )

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    def _execute_buy(
        self,
        code: str,
        name: str,
        strategy: BaseStrategy,
        split_cfg: SplitBuyConfig,
        current_price: float,
        existing: bool = False,
    ) -> bool:
        available_cash = self._get_available_cash()
        qty = strategy.calculate_buy_quantity(
            step=split_cfg.step,
            available_cash=available_cash,
            current_price=current_price,
            total_investment=self._total_investment,
        )
        if qty <= 0:
            logger.warning(
                "Calculated qty=0 for code=%s step=%d price=%.0f",
                code, split_cfg.step, current_price,
            )
            return False

        result = self._orders.buy_market(code, qty)
        if result < 0:
            logger.error(
                "buy_market failed for code=%s qty=%d result=%d", code, qty, result
            )
            return False

        if existing:
            self._portfolio._merge_position(code, qty, current_price)
        else:
            self._portfolio.add_position(
                code=code,
                name=name,
                strategy_name=strategy.name,
                quantity=qty,
                price=current_price,
            )

        self._portfolio.mark_buy_step_done(code, split_cfg.step)
        logger.info(
            "Bought code=%s qty=%d price=%.0f step=%d strategy=%s",
            code, qty, current_price, split_cfg.step, strategy.name,
        )
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_available_cash(self) -> float:
        try:
            balance = self._orders.get_balance()
            raw = balance.get("주문가능금액", "0").replace(",", "").strip()
            return float(raw) if raw else 0.0
        except Exception:
            logger.exception("Failed to fetch available cash; using 0.")
            return 0.0

    def calculate_investment_amount(self, strategy: BaseStrategy, step: int) -> float:
        """Return the KRW budget for a given strategy and step."""
        for split in strategy.config.buy_splits:
            if split.step == step:
                return self._total_investment * split.ratio
        return 0.0
