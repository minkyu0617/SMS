from typing import Any, Dict, Tuple

from core.strategy.base import BaseStrategy, StrategyConfig
from utils.logger import get_logger

logger = get_logger(__name__)

VOLUME_MULTIPLIER = 1.5  # current volume must exceed MA20 volume by this factor


class MomentumStrategy(BaseStrategy):
    """Momentum strategy: buys on condition entry when volume confirms the move.

    Buy signal: stock enters condition search AND current volume > MA20 volume * 1.5
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
        """Return True when condition is entered and volume confirms momentum."""
        volume = self._parse_int(stock_info.get("거래량", "0"))
        ma20_volume = self._parse_int(stock_info.get("ma20_volume", "0"))

        if ma20_volume > 0 and volume < ma20_volume * VOLUME_MULTIPLIER:
            logger.debug(
                "MomentumStrategy: code=%s volume check failed (vol=%d, ma20=%d)",
                code, volume, ma20_volume,
            )
            return False

        logger.info("MomentumStrategy: buy signal for code=%s price=%.0f", code, current_price)
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
            logger.info("MomentumStrategy: sell triggered (%s) for code=%s", reason, position.code)
            return True, reason

        if self._check_trailing_stop(profit_pct, position.highest_price, current_price):
            drawdown = (current_price - position.highest_price) / position.highest_price * 100.0
            reason = (
                f"trailing_stop: profit={profit_pct:.2f}%, "
                f"drawdown_from_peak={drawdown:.2f}%"
            )
            logger.info("MomentumStrategy: sell triggered (%s) for code=%s", reason, position.code)
            return True, reason

        return False, ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_int(value: Any) -> int:
        try:
            return int(str(value).replace(",", "").strip())
        except (ValueError, TypeError):
            return 0
