import os
from typing import Dict, List, Optional

import yaml

from core.strategy.base import BaseStrategy, SellConfig, SplitBuyConfig, StrategyConfig
from utils.logger import get_logger

logger = get_logger(__name__)

# Registry maps strategy config names to concrete strategy classes.
# Import is deferred to avoid circular dependencies.
_STRATEGY_REGISTRY: Dict[str, str] = {
    "모멘텀 전략": "core.strategy.strategies.momentum.MomentumStrategy",
    "돌파 전략": "core.strategy.strategies.breakout.BreakoutStrategy",
}


def _import_strategy_class(dotted_path: str):
    """Dynamically import a strategy class by dotted module path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class StrategyManager:
    """Loads and manages all trading strategies from YAML configuration files."""

    def __init__(self, config_dir: str) -> None:
        self._config_dir = config_dir
        self._strategies: Dict[str, BaseStrategy] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_strategies(self) -> None:
        """Scan config_dir for *.yaml files and instantiate strategy objects."""
        strategies_dir = os.path.join(self._config_dir, "strategies")
        if not os.path.isdir(strategies_dir):
            logger.warning("Strategies directory not found: %s", strategies_dir)
            return

        for filename in sorted(os.listdir(strategies_dir)):
            if not filename.endswith(".yaml"):
                continue
            filepath = os.path.join(strategies_dir, filename)
            try:
                self._load_strategy_file(filepath)
            except Exception:
                logger.exception("Failed to load strategy file: %s", filepath)

        logger.info("Loaded %d strategies: %s", len(self._strategies), list(self._strategies))

    def _load_strategy_file(self, filepath: str) -> None:
        with open(filepath, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        sell_data = data.get("sell", {})
        sell_cfg = SellConfig(
            stop_loss_pct=float(sell_data.get("stop_loss_pct", -8.0)),
            trailing_stop_pct=float(sell_data.get("trailing_stop_pct", 3.0)),
            trailing_activate_pct=float(sell_data.get("trailing_activate_pct", 5.0)),
        )

        splits = [
            SplitBuyConfig(
                step=int(s["step"]),
                ratio=float(s["ratio"]),
                drop_pct=float(s["drop_pct"]),
            )
            for s in data.get("buy_splits", [])
        ]

        config = StrategyConfig(
            name=data["name"],
            enabled=bool(data.get("enabled", False)),
            condition_name=data.get("condition_name", ""),
            buy_splits=splits,
            sell=sell_cfg,
        )

        dotted_path = _STRATEGY_REGISTRY.get(config.name)
        if dotted_path is None:
            logger.warning("No strategy class registered for name '%s'; skipping.", config.name)
            return

        strategy_cls = _import_strategy_class(dotted_path)
        strategy = strategy_cls(config)
        self._strategies[config.name] = strategy
        logger.debug("Registered strategy: %s (enabled=%s)", config.name, config.enabled)

    # ------------------------------------------------------------------
    # Query / mutate
    # ------------------------------------------------------------------

    def get_strategy(self, name: str) -> Optional[BaseStrategy]:
        return self._strategies.get(name)

    def get_enabled_strategies(self) -> List[BaseStrategy]:
        return [s for s in self._strategies.values() if s.is_enabled]

    def get_all_strategies(self) -> Dict[str, BaseStrategy]:
        return dict(self._strategies)

    def enable_strategy(self, name: str) -> bool:
        strategy = self._strategies.get(name)
        if strategy is None:
            logger.error("Strategy '%s' not found.", name)
            return False
        strategy.enable()
        logger.info("Strategy enabled: %s", name)
        return True

    def disable_strategy(self, name: str) -> bool:
        strategy = self._strategies.get(name)
        if strategy is None:
            logger.error("Strategy '%s' not found.", name)
            return False
        strategy.disable()
        logger.info("Strategy disabled: %s", name)
        return True

    def register_strategy(self, name: str, strategy: BaseStrategy) -> None:
        """Programmatically register a strategy instance (e.g. for testing)."""
        self._strategies[name] = strategy

    def get_strategy_for_condition(self, condition_name: str) -> Optional[BaseStrategy]:
        """Return the first strategy whose condition_name matches, or None."""
        for strategy in self._strategies.values():
            if strategy.config.condition_name == condition_name:
                return strategy
        return None
