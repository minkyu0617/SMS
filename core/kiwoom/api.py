# NOTE: Kiwoom OpenAPI+ is a Windows-only COM component.
# This module must be run on a Windows machine with Kiwoom OpenAPI+ installed.
# PyQt5 QAxWidget is used as the COM automation wrapper.

import sys
import os
import time
import logging
import asyncio
from typing import Callable, Dict, List, Optional, Any

from utils.logger import get_logger

logger = get_logger(__name__)

try:
    from PyQt5.QAxContainer import QAxWidget
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QEventLoop, QTimer
    _PYQT_AVAILABLE = True
except ImportError:
    logger.warning("PyQt5 not available. KiwoomAPI will run in stub mode.")
    _PYQT_AVAILABLE = False


class KiwoomAPI:
    """Wrapper around Kiwoom OpenAPI+ COM object via QAxWidget.

    All methods that interact with the COM object will raise RuntimeError
    when PyQt5 / Kiwoom OpenAPI+ is not available.
    """

    REALTYPE_CURRENT_PRICE = "주식체결"
    TR_STOCK_INFO = "opt10001"
    TR_HOLDINGS = "opw00018"
    TR_BALANCE = "opw00001"

    def __init__(self) -> None:
        self._ocx: Optional[Any] = None
        self._login_event: Optional[Any] = None
        self._tr_event_loop: Optional[Any] = None
        self._tr_data: Dict[str, Any] = {}
        self._callbacks: Dict[str, List[Callable]] = {
            "condition": [],
            "realtime": [],
            "order": [],
        }

        if _PYQT_AVAILABLE:
            self._ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
            self._connect_events()
        else:
            logger.warning("Running without Kiwoom API (stub mode).")

    # ------------------------------------------------------------------
    # Event wiring
    # ------------------------------------------------------------------

    def _connect_events(self) -> None:
        if self._ocx is None:
            return
        self._ocx.OnEventConnect.connect(self._on_event_connect)
        self._ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        self._ocx.OnReceiveRealData.connect(self._on_receive_real_data)
        self._ocx.OnReceiveMsg.connect(self._on_receive_msg)
        self._ocx.OnReceiveConditionVer.connect(self._on_receive_condition_ver)
        self._ocx.OnReceiveTrCondition.connect(self._on_receive_tr_condition)
        self._ocx.OnReceiveRealCondition.connect(self._on_receive_real_condition)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self) -> bool:
        """Trigger CommConnect and block until login completes."""
        if self._ocx is None:
            logger.error("OCX not initialised; cannot login.")
            return False

        self._login_event = QEventLoop()
        self._ocx.dynamicCall("CommConnect()")
        self._login_event.exec_()
        return True

    def _on_event_connect(self, err_code: int) -> None:
        if err_code == 0:
            logger.info("Kiwoom login succeeded.")
        else:
            logger.error("Kiwoom login failed. error_code=%d", err_code)
        if self._login_event:
            self._login_event.exit()

    # ------------------------------------------------------------------
    # Condition search
    # ------------------------------------------------------------------

    def get_condition_list(self) -> Dict[int, str]:
        """Load condition list and return {index: name} mapping."""
        if self._ocx is None:
            return {}

        self._ocx.dynamicCall("GetConditionLoad()")
        raw: str = self._ocx.dynamicCall("GetConditionNameList()")
        conditions: Dict[int, str] = {}
        if raw:
            for item in raw.split(";"):
                if "^" in item:
                    idx_str, name = item.split("^", 1)
                    try:
                        conditions[int(idx_str)] = name
                    except ValueError:
                        pass
        logger.debug("Loaded %d conditions.", len(conditions))
        return conditions

    def send_condition(
        self,
        screen_no: str,
        condition_name: str,
        index: int,
        search_type: int = 1,
    ) -> int:
        """Start condition search (search_type=1 for realtime)."""
        if self._ocx is None:
            return -1
        result: int = self._ocx.dynamicCall(
            "SendCondition(QString, QString, int, int)",
            screen_no,
            condition_name,
            index,
            search_type,
        )
        logger.info(
            "SendCondition screen=%s name=%s index=%d type=%d -> %d",
            screen_no,
            condition_name,
            index,
            search_type,
            result,
        )
        return result

    def stop_condition(self, screen_no: str, condition_name: str, index: int) -> None:
        """Stop realtime condition search."""
        if self._ocx is None:
            return
        self._ocx.dynamicCall(
            "SendConditionStop(QString, QString, int)",
            screen_no,
            condition_name,
            index,
        )

    # ------------------------------------------------------------------
    # TR data
    # ------------------------------------------------------------------

    def get_stock_info(self, code: str) -> Dict[str, Any]:
        """Query opt10001 to get basic stock information."""
        if self._ocx is None:
            return {}

        screen_no = "1000"
        self._ocx.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        self._tr_event_loop = QEventLoop()
        self._ocx.dynamicCall(
            "CommRqData(QString, QString, int, QString)",
            "stock_info",
            self.TR_STOCK_INFO,
            0,
            screen_no,
        )
        self._tr_event_loop.exec_()
        return self._tr_data.get("stock_info", {})

    def _parse_tr_data(self, rq_name: str, tr_code: str, record_name: str, fields: List[str]) -> Dict[str, str]:
        """Helper to extract single-record TR output fields."""
        result: Dict[str, str] = {}
        if self._ocx is None:
            return result
        for field in fields:
            value: str = self._ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                tr_code,
                record_name,
                0,
                field,
            ).strip()
            result[field] = value
        return result

    # ------------------------------------------------------------------
    # Order
    # ------------------------------------------------------------------

    def send_order(
        self,
        order_type: int,
        screen_no: str,
        acc_no: str,
        code: str,
        qty: int,
        price: int,
        hoga_gb: str,
    ) -> int:
        """Wrap SendOrder COM call.

        order_type: 1=buy, 2=sell, 3=cancel_buy, 4=cancel_sell
        hoga_gb: "00"=limit, "03"=market
        """
        if self._ocx is None:
            return -1
        result: int = self._ocx.dynamicCall(
            "SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
            "order",
            screen_no,
            acc_no,
            order_type,
            code,
            qty,
            price,
            hoga_gb,
            "",
        )
        logger.info(
            "SendOrder type=%d code=%s qty=%d price=%d hoga=%s -> %d",
            order_type,
            code,
            qty,
            price,
            hoga_gb,
            result,
        )
        return result

    # ------------------------------------------------------------------
    # GetCommData helpers (public)
    # ------------------------------------------------------------------

    def get_comm_data(self, tr_code: str, record_name: str, index: int, field: str) -> str:
        if self._ocx is None:
            return ""
        return self._ocx.dynamicCall(
            "GetCommData(QString, QString, int, QString)",
            tr_code,
            record_name,
            index,
            field,
        ).strip()

    def get_repeat_cnt(self, tr_code: str, record_name: str) -> int:
        if self._ocx is None:
            return 0
        return int(
            self._ocx.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, record_name)
        )

    def get_comm_real_data(self, code: str, fid: int) -> str:
        if self._ocx is None:
            return ""
        return self._ocx.dynamicCall(
            "GetCommRealData(QString, int)", code, fid
        ).strip()

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def register_condition_callback(self, callback: Callable) -> None:
        self._callbacks["condition"].append(callback)

    def register_realtime_callback(self, callback: Callable) -> None:
        self._callbacks["realtime"].append(callback)

    def register_order_callback(self, callback: Callable) -> None:
        self._callbacks["order"].append(callback)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_receive_tr_data(
        self,
        screen_no: str,
        rq_name: str,
        tr_code: str,
        record_name: str,
        prev_next: str,
        data_len: int,
        err_code: str,
        msg: str,
        spl_msg: str,
    ) -> None:
        logger.debug("OnReceiveTrData rq=%s tr=%s", rq_name, tr_code)

        if tr_code == self.TR_STOCK_INFO:
            fields = ["종목명", "현재가", "등락률", "거래량", "시가", "고가", "저가", "기준가"]
            self._tr_data["stock_info"] = self._parse_tr_data(rq_name, tr_code, record_name, fields)

        elif tr_code == self.TR_HOLDINGS:
            cnt = self.get_repeat_cnt(tr_code, record_name)
            holdings = []
            for i in range(cnt):
                item = {}
                for f in ["종목번호", "종목명", "보유수량", "매입가", "현재가", "평가손익", "수익률(%)"]:
                    item[f] = self._ocx.dynamicCall(
                        "GetCommData(QString, QString, int, QString)",
                        tr_code, record_name, i, f
                    ).strip()
                holdings.append(item)
            self._tr_data["holdings"] = holdings

        elif tr_code == self.TR_BALANCE:
            fields = ["예수금", "출금가능금액", "주문가능금액"]
            self._tr_data["balance"] = self._parse_tr_data(rq_name, tr_code, record_name, fields)

        if self._tr_event_loop and self._tr_event_loop.isRunning():
            self._tr_event_loop.exit()

    def _on_receive_real_data(self, code: str, real_type: str, real_data: str) -> None:
        for cb in self._callbacks["realtime"]:
            try:
                cb(code, real_type, real_data)
            except Exception:
                logger.exception("Error in realtime callback for code=%s", code)

    def _on_receive_msg(self, screen_no: str, rq_name: str, tr_code: str, msg: str) -> None:
        logger.info("OnReceiveMsg screen=%s rq=%s tr=%s msg=%s", screen_no, rq_name, tr_code, msg)

    def _on_receive_condition_ver(self, ret: int, msg: str) -> None:
        logger.debug("OnReceiveConditionVer ret=%d msg=%s", ret, msg)

    def _on_receive_tr_condition(
        self,
        screen_no: str,
        code_list: str,
        condition_name: str,
        index: int,
        next_flag: int,
    ) -> None:
        logger.debug(
            "OnReceiveTrCondition screen=%s condition=%s codes=%s",
            screen_no,
            condition_name,
            code_list,
        )
        codes = [c for c in code_list.split(";") if c]
        for cb in self._callbacks["condition"]:
            try:
                for code in codes:
                    cb(code, condition_name, "I")
            except Exception:
                logger.exception("Error in condition callback (tr) for condition=%s", condition_name)

    def _on_receive_real_condition(
        self, code: str, kind: str, condition_name: str, condition_index: str
    ) -> None:
        """Realtime condition event: kind='I' (in) or 'D' (out)."""
        logger.debug(
            "OnReceiveRealCondition code=%s kind=%s condition=%s",
            code,
            kind,
            condition_name,
        )
        for cb in self._callbacks["condition"]:
            try:
                cb(code, condition_name, kind)
            except Exception:
                logger.exception(
                    "Error in condition callback (real) for code=%s condition=%s",
                    code,
                    condition_name,
                )

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    def get_login_info(self, tag: str) -> str:
        if self._ocx is None:
            return ""
        return self._ocx.dynamicCall("GetLoginInfo(QString)", tag)
