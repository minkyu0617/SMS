from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SplitBuyConfig:
    """Configuration for a single split-buy step."""
    step: int
    ratio: float          # fraction of per-step budget to deploy (0–1)
    drop_pct: float       # price must have dropped this % from entry to trigger (<=0)


@dataclass
class SellConfig:
    """Sell / exit configuration."""
    stop_loss_pct: float          # hard stop loss, e.g. -8.0
    trailing_stop_pct: float      # trailing stop distance from peak, e.g. 3.0
    trailing_activate_pct: float  # profit % required to activate trailing stop, e.g. 5.0


@dataclass
class StrategyConfig:
    """Full strategy configuration loaded from YAML."""
    name: str
    enabled: bool
    condition_name: str
    buy_splits: List[SplitBuyConfig] = field(default_factory=list)
    sell: SellConfig = field(
        default_factory=lambda: SellConfig(
            stop_loss_pct=-8.0,
            trailing_stop_pct=3.0,
            trailing_activate_pct=5.0,
        )
    )


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    @property
    def is_enabled(self) -> bool:
        return self.config.enabled

    @property
    def name(self) -> str:
        return self.config.name

    def enable(self) -> None:
        self.config.enabled = True

    def disable(self) -> None:
        self.config.enabled = False

    # ------------------------------------------------------------------
    # Abstract methods — implemented by concrete strategies
    # ------------------------------------------------------------------

    @abstractmethod
    def should_buy(
        self,
        code: str,
        current_price: float,
        stock_info: Dict[str, Any],
    ) -> bool:
        """Return True if the strategy wants to initiate a buy for this stock."""

    @abstractmethod
    def should_sell(
        self,
        position: Any,
        current_price: float,
    ) -> Tuple[bool, str]:
        """Return (should_sell, reason).  reason is empty string when not selling."""

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    def calculate_buy_quantity(
        self,
        step: int,
        available_cash: float,
        current_price: float,
        total_investment: float,
    ) -> int:
        """Calculate the number of shares to buy for a given split step.

        Uses the ratio defined in buy_splits[step-1] applied to total_investment.
        Returns 0 when price or cash is insufficient.
        """
        if current_price <= 0:
            return 0

        split_cfg = self._get_split_config(step)
        if split_cfg is None:
            return 0

        budget = total_investment * split_cfg.ratio
        budget = min(budget, available_cash)
        qty = int(budget // current_price)
        return max(qty, 0)

    def get_next_buy_step(self, position: Any) -> Optional[SplitBuyConfig]:
        """Return the next pending SplitBuyConfig, or None if all steps done."""
        done_steps = set(getattr(position, "buy_steps_done", []))
        for split in sorted(self.config.buy_splits, key=lambda s: s.step):
            if split.step not in done_steps:
                return split
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_split_config(self, step: int) -> Optional[SplitBuyConfig]:
        for s in self.config.buy_splits:
            if s.step == step:
                return s
        return None

    def _check_stop_loss(self, profit_pct: float) -> bool:
        return profit_pct <= self.config.sell.stop_loss_pct

    def _check_trailing_stop(self, profit_pct: float, highest_price: float, current_price: float) -> bool:
        """Return True when trailing stop is triggered."""
        sell_cfg = self.config.sell
        if profit_pct < sell_cfg.trailing_activate_pct:
            return False
        if highest_price <= 0:
            return False
        drawdown_pct = (current_price - highest_price) / highest_price * 100.0
        return drawdown_pct <= -sell_cfg.trailing_stop_pct

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.config.name!r}, enabled={self.config.enabled})"
