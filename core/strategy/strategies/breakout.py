from typing import Any, Dict, Tuple

from core.strategy.base import BaseStrategy, StrategyConfig
from utils.logger import get_logger

logger = get_logger(__name__)

HIGH_52W_PROXIMITY_PCT = 3.0  # current price must be within this % of 52-week high


class BreakoutStrategy(BaseStrategy):
    """Breakout strategy: buys when stock enters condition near its 52-week high.

    Buy signal: condition entry AND current price is within HIGH_52W_PROXIMITY_PCT
                of the 52-week high price.
    Sell signal: hard stop-loss OR trailing stop once activate threshold is reached.
    """

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)

    # ------------------------------------------------------------------
    # Buy logic
    # ------------------------------------------------------------------

    def should_buy(
        self,
        code: str,
        current_price: float,
        stock_info: Dict[str, Any],
    ) -> bool:
        """Return True when price is close to 52-week high (breakout zone)."""
        high_52w = self._parse_float(stock_info.get("52주최고가", "0"))

        if high_52w > 0:
            proximity_pct = (current_price - high_52w) / high_52w * 100.0
            # current price should be within HIGH_52W_PROXIMITY_PCT below the 52w high
            # (positive means already above, which is a valid breakout)
            if proximity_pct < -HIGH_52W_PROXIMITY_PCT:
                logger.debug(
                    "BreakoutStrategy: code=%s not near 52w high (current=%.0f, high=%.0f, proximity=%.2f%%)",
                    code, current_price, high_52w, proximity_pct,
                )
                return False

        logger.info("BreakoutStrategy: buy signal for code=%s price=%.0f", code, current_price)
        return True

    # ------------------------------------------------------------------
    # Sell logic
    # ------------------------------------------------------------------

    def should_sell(
        self,
        position: Any,
        current_price: float,
    ) -> Tuple[bool, str]:
        """Check stop-loss then trailing stop."""
        profit_pct = position.profit_pct

        if self._check_stop_loss(profit_pct):
            reason = f"stop_loss: profit={profit_pct:.2f}% <= {self.config.sell.stop_loss_pct}%"
            logger.info("BreakoutStrategy: sell triggered (%s) for code=%s", reason, position.code)
            return True, reason

        if self._check_trailing_stop(profit_pct, position.highest_price, current_price):
            drawdown = (current_price - position.highest_price) / position.highest_price * 100.0
            reason = (
                f"trailing_stop: profit={profit_pct:.2f}%, "
                f"drawdown_from_peak={drawdown:.2f}%"
            )
            logger.info("BreakoutStrategy: sell triggered (%s) for code=%s", reason, position.code)
            return True, reason

        return False, ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_float(value: Any) -> float:
        try:
            return float(str(value).replace(",", "").strip())
        except (ValueError, TypeError):
            return 0.0
