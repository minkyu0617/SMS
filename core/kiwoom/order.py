# NOTE: Kiwoom OpenAPI+ is a Windows-only COM component.
# This module must be run on a Windows machine with Kiwoom OpenAPI+ installed.

from typing import Any, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

_SCREEN_BUY = "3001"
_SCREEN_SELL = "3002"
_SCREEN_CANCEL = "3003"
_SCREEN_HOLDINGS = "4001"
_SCREEN_BALANCE = "4002"

HOGA_MARKET = "03"
HOGA_LIMIT = "00"

ORDER_BUY = 1
ORDER_SELL = 2
ORDER_CANCEL_BUY = 3
ORDER_CANCEL_SELL = 4


class OrderManager:
    """Wraps Kiwoom order-related COM calls."""

    def __init__(self, kiwoom_api, account_number: str) -> None:
        self._api = kiwoom_api
        self._account = account_number
        self._order_results: List[Dict[str, Any]] = []
        self._api.register_order_callback(self._on_order_event)

    # ------------------------------------------------------------------
    # Buy orders
    # ------------------------------------------------------------------

    def buy_market(self, code: str, qty: int) -> int:
        """Place a market-price buy order. Returns SendOrder result code."""
        logger.info("buy_market code=%s qty=%d", code, qty)
        return self._api.send_order(
            order_type=ORDER_BUY,
            screen_no=_SCREEN_BUY,
            acc_no=self._account,
            code=code,
            qty=qty,
            price=0,
            hoga_gb=HOGA_MARKET,
        )

    def buy_limit(self, code: str, qty: int, price: int) -> int:
        """Place a limit-price buy order."""
        logger.info("buy_limit code=%s qty=%d price=%d", code, qty, price)
        return self._api.send_order(
            order_type=ORDER_BUY,
            screen_no=_SCREEN_BUY,
            acc_no=self._account,
            code=code,
            qty=qty,
            price=price,
            hoga_gb=HOGA_LIMIT,
        )

    # ------------------------------------------------------------------
    # Sell orders
    # ------------------------------------------------------------------

    def sell_market(self, code: str, qty: int) -> int:
        """Place a market-price sell order."""
        logger.info("sell_market code=%s qty=%d", code, qty)
        return self._api.send_order(
            order_type=ORDER_SELL,
            screen_no=_SCREEN_SELL,
            acc_no=self._account,
            code=code,
            qty=qty,
            price=0,
            hoga_gb=HOGA_MARKET,
        )

    def sell_limit(self, code: str, qty: int, price: int) -> int:
        """Place a limit-price sell order."""
        logger.info("sell_limit code=%s qty=%d price=%d", code, qty, price)
        return self._api.send_order(
            order_type=ORDER_SELL,
            screen_no=_SCREEN_SELL,
            acc_no=self._account,
            code=code,
            qty=qty,
            price=price,
            hoga_gb=HOGA_LIMIT,
        )

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def cancel_order(self, screen_no: str, order_no: str, code: str, qty: int) -> int:
        """Cancel an outstanding order."""
        logger.info("cancel_order order_no=%s code=%s qty=%d", order_no, code, qty)
        return self._api.send_order(
            order_type=ORDER_CANCEL_BUY,
            screen_no=screen_no,
            acc_no=self._account,
            code=code,
            qty=qty,
            price=0,
            hoga_gb=HOGA_MARKET,
        )

    # ------------------------------------------------------------------
    # Account queries
    # ------------------------------------------------------------------

    def get_holdings(self) -> List[Dict[str, str]]:
        """Query current holdings via opw00018 TR. Returns list of holding dicts."""
        if self._api._ocx is None:
            logger.warning("OCX not available; returning empty holdings.")
            return []

        try:
            from PyQt5.QtCore import QEventLoop

            self._api._ocx.dynamicCall("SetInputValue(QString, QString)", "계좌번호", self._account)
            self._api._ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호", "")
            self._api._ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호입력매체구분", "00")
            self._api._ocx.dynamicCall("SetInputValue(QString, QString)", "조회구분", "1")
            self._api._tr_event_loop = QEventLoop()
            self._api._ocx.dynamicCall(
                "CommRqData(QString, QString, int, QString)",
                "holdings",
                "opw00018",
                0,
                _SCREEN_HOLDINGS,
            )
            self._api._tr_event_loop.exec_()
            return self._api._tr_data.get("holdings", [])
        except Exception:
            logger.exception("Failed to query holdings.")
            return []

    def get_balance(self) -> Dict[str, str]:
        """Query deposit balance via opw00001 TR."""
        if self._api._ocx is None:
            logger.warning("OCX not available; returning empty balance.")
            return {}

        try:
            from PyQt5.QtCore import QEventLoop

            self._api._ocx.dynamicCall("SetInputValue(QString, QString)", "계좌번호", self._account)
            self._api._ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호", "")
            self._api._ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호입력매체구분", "00")
            self._api._ocx.dynamicCall("SetInputValue(QString, QString)", "조회구분", "1")
            self._api._tr_event_loop = QEventLoop()
            self._api._ocx.dynamicCall(
                "CommRqData(QString, QString, int, QString)",
                "balance",
                "opw00001",
                0,
                _SCREEN_BALANCE,
            )
            self._api._tr_event_loop.exec_()
            return self._api._tr_data.get("balance", {})
        except Exception:
            logger.exception("Failed to query balance.")
            return {}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_order_event(self, *args: Any) -> None:
        logger.debug("Order event: %s", args)
