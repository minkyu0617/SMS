# NOTE: Kiwoom OpenAPI+ requires Windows + Kiwoom OpenAPI+ installed.
# Run this on a Windows machine with PyQt5 and the COM components registered.

import asyncio
import os
import sys

import yaml
from dotenv import load_dotenv

load_dotenv()


def _load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TradingEngine:
    """Wires all components together and drives the main event loop."""

    def __init__(self, config: dict) -> None:
        self._cfg = config
        self._setup_components()

    def _setup_components(self) -> None:
        from core.kiwoom.api import KiwoomAPI
        from core.kiwoom.condition import ConditionSearcher
        from core.kiwoom.order import OrderManager
        from core.kiwoom.realtime import RealtimeManager
        from core.strategy.manager import StrategyManager
        from core.trading.buy_manager import BuyManager
        from core.trading.portfolio import Portfolio
        from core.trading.sell_manager import SellManager
        from telegram_bot.bot import TradingBot

        kiwoom_cfg = self._cfg["kiwoom"]
        tg_cfg = self._cfg["telegram"]
        trade_cfg = self._cfg["trading"]

        account = os.getenv("KIWOOM_ACCOUNT") or kiwoom_cfg.get("account_number", "")
        tg_token = os.getenv("TELEGRAM_TOKEN") or tg_cfg.get("token", "")
        raw_users = os.getenv("TELEGRAM_ALLOWED_USERS", "")
        allowed_users = (
            [int(u) for u in raw_users.split(",") if u.strip().isdigit()]
            or [int(u) for u in tg_cfg.get("allowed_users", [])]
        )

        self.kiwoom = KiwoomAPI()
        self.order_manager = OrderManager(self.kiwoom, account)
        self.realtime_manager = RealtimeManager(self.kiwoom)
        self.condition_searcher = ConditionSearcher(self.kiwoom)

        config_dir = os.path.join(os.path.dirname(__file__), "config")
        self.strategy_manager = StrategyManager(config_dir)
        self.strategy_manager.load_strategies()

        self.portfolio = Portfolio()
        self.buy_manager = BuyManager(
            order_manager=self.order_manager,
            portfolio=self.portfolio,
            total_investment=float(trade_cfg.get("total_investment", 10_000_000)),
            max_stocks=int(trade_cfg.get("max_stocks", 5)),
        )
        self.sell_manager = SellManager(
            order_manager=self.order_manager,
            portfolio=self.portfolio,
            strategy_manager=self.strategy_manager,
        )

        self.telegram_bot = TradingBot(
            token=tg_token,
            allowed_users=allowed_users,
            trading_engine=self,
        )

        self.condition_searcher.register_signal_callback(self._on_condition_signal)
        self.realtime_manager.register_price_callback(self._on_price_update)

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def start(self) -> None:
        from utils.logger import get_logger
        logger = get_logger(__name__)

        logger.info("Logging into Kiwoom...")
        self.kiwoom.login()

        logger.info("Loading condition list...")
        self.condition_searcher.load_conditions()

        logger.info("Starting condition searches for active strategies...")
        for strategy in self.strategy_manager.get_enabled_strategies():
            self.condition_searcher.start_condition(strategy.config.condition_name)

        logger.info("Building Telegram bot...")
        self.telegram_bot.build()

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_condition_signal(self, code: str, condition_name: str, kind: str) -> None:
        strategy = self.strategy_manager.get_strategy_for_condition(condition_name)
        if strategy is None or not strategy.is_enabled:
            return

        if kind == "I":
            stock_info = self.kiwoom.get_stock_info(code)
            current_price = abs(int(stock_info.get("현재가", "0").replace(",", "") or 0))
            name = stock_info.get("종목명", code)
            if current_price > 0:
                self.realtime_manager.subscribe(code)
                self.buy_manager.process_candidate(
                    code=code,
                    name=name,
                    strategy=strategy,
                    current_price=float(current_price),
                    stock_info=stock_info,
                )
        elif kind == "D":
            if not self.portfolio.has_position(code):
                self.realtime_manager.unsubscribe(code)

    def _on_price_update(self, code: str, snapshot) -> None:
        current_price = float(abs(snapshot.current_price))
        if current_price > 0:
            self.sell_manager.on_price_update(code, current_price)
            strategy = None
            pos = self.portfolio.get_position(code)
            if pos:
                strategy = self.strategy_manager.get_strategy(pos.strategy_name)
            if strategy:
                self.buy_manager.check_additional_buy(code, strategy, current_price)

    async def on_strategy_enabled(self, name: str) -> None:
        strategy = self.strategy_manager.get_strategy(name)
        if strategy:
            self.condition_searcher.start_condition(strategy.config.condition_name)

    async def on_strategy_disabled(self, name: str) -> None:
        strategy = self.strategy_manager.get_strategy(name)
        if strategy:
            self.condition_searcher.stop_condition(strategy.config.condition_name)

    # ------------------------------------------------------------------
    # Periodic sell check (fallback when realtime is not available)
    # ------------------------------------------------------------------

    async def run_sell_check_loop(self) -> None:
        from utils.logger import get_logger
        logger = get_logger(__name__)
        while True:
            try:
                self.sell_manager.check_and_sell_all()
            except Exception:
                logger.exception("Error in sell check loop.")
            await asyncio.sleep(60)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    config_path = os.path.join(os.path.dirname(__file__), "config", "config.yaml")
    config = _load_config(config_path)

    try:
        import qasync
        from PyQt5.QtWidgets import QApplication

        app = QApplication(sys.argv)
        engine = TradingEngine(config)
        engine.start()

        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        with loop:
            loop.create_task(engine.run_sell_check_loop())
            tg_app = engine.telegram_bot.get_application()
            loop.run_forever()

    except ImportError:
        from utils.logger import get_logger
        logger = get_logger(__name__)
        logger.error(
            "PyQt5 / qasync not available. "
            "Install dependencies and run on Windows with Kiwoom OpenAPI+."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
