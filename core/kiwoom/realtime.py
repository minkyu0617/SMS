# NOTE: Kiwoom OpenAPI+ is a Windows-only COM component.
# This module must be run on a Windows machine with Kiwoom OpenAPI+ installed.

from typing import Callable, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# FID constants for common realtime fields
FID_CURRENT_PRICE = 10    # 현재가
FID_CHANGE_RATE = 12      # 등락률
FID_VOLUME = 15           # 거래량
FID_BID_PRICE = 41        # 매수호가1
FID_ASK_PRICE = 51        # 매도호가1
FID_HIGH_PRICE = 17       # 고가
FID_LOW_PRICE = 18        # 저가
FID_OPEN_PRICE = 16       # 시가

REALTYPE_STOCK_TICK = "주식체결"
REALTYPE_BID_ASK = "주식호가잔량"


class RealtimeData:
    """Snapshot of realtime data for a single stock."""

    __slots__ = (
        "code",
        "current_price",
        "change_rate",
        "volume",
        "bid_price",
        "ask_price",
        "high_price",
        "low_price",
        "open_price",
    )

    def __init__(self, code: str) -> None:
        self.code = code
        self.current_price: int = 0
        self.change_rate: float = 0.0
        self.volume: int = 0
        self.bid_price: int = 0
        self.ask_price: int = 0
        self.high_price: int = 0
        self.low_price: int = 0
        self.open_price: int = 0

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"RealtimeData(code={self.code}, price={self.current_price}, "
            f"rate={self.change_rate:.2f}%, vol={self.volume})"
        )


class RealtimeManager:
    """Manages realtime data subscriptions and caches the latest snapshot per stock."""

    def __init__(self, kiwoom_api) -> None:
        self._api = kiwoom_api
        self._subscribed: Dict[str, str] = {}   # code -> screen_no
        self._snapshots: Dict[str, RealtimeData] = {}
        self._price_callbacks: List[Callable[[str, RealtimeData], None]] = []
        self._screen_base = 5000
        self._screen_counter = 0

        self._api.register_realtime_callback(self.on_realtime_data)

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(self, code: str, fid_list: Optional[str] = None) -> None:
        """Subscribe to realtime data for a stock code."""
        if code in self._subscribed:
            return

        if fid_list is None:
            fid_list = f"{FID_CURRENT_PRICE};{FID_CHANGE_RATE};{FID_VOLUME};" \
                       f"{FID_BID_PRICE};{FID_ASK_PRICE};{FID_HIGH_PRICE};" \
                       f"{FID_LOW_PRICE};{FID_OPEN_PRICE}"

        screen_no = str(self._screen_base + self._screen_counter)
        self._screen_counter += 1

        if self._api._ocx is not None:
            self._api._ocx.dynamicCall(
                "SetRealReg(QString, QString, QString, QString)",
                screen_no,
                code,
                fid_list,
                "0",
            )

        self._subscribed[code] = screen_no
        if code not in self._snapshots:
            self._snapshots[code] = RealtimeData(code)
        logger.info("Subscribed to realtime data for code=%s screen=%s", code, screen_no)

    def unsubscribe(self, code: str) -> None:
        """Unsubscribe from realtime data for a stock code."""
        screen_no = self._subscribed.pop(code, None)
        if screen_no is None:
            return

        if self._api._ocx is not None:
            self._api._ocx.dynamicCall(
                "SetRealRemove(QString, QString)",
                screen_no,
                code,
            )

        logger.info("Unsubscribed from realtime data for code=%s", code)

    def unsubscribe_all(self) -> None:
        for code in list(self._subscribed):
            self.unsubscribe(code)

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def register_price_callback(self, callback: Callable[[str, RealtimeData], None]) -> None:
        """Register a callback(code, snapshot) fired on each price update."""
        self._price_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def get_snapshot(self, code: str) -> Optional[RealtimeData]:
        return self._snapshots.get(code)

    def get_current_price(self, code: str) -> int:
        snapshot = self._snapshots.get(code)
        return abs(snapshot.current_price) if snapshot else 0

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    def on_realtime_data(self, code: str, real_type: str, data: str) -> None:
        """Process incoming realtime data dispatched by KiwoomAPI."""
        if code not in self._subscribed:
            return

        snapshot = self._snapshots.setdefault(code, RealtimeData(code))

        if real_type == REALTYPE_STOCK_TICK:
            self._parse_tick(code, snapshot)

        for cb in self._price_callbacks:
            try:
                cb(code, snapshot)
            except Exception:
                logger.exception("Error in price callback for code=%s", code)

    def _parse_tick(self, code: str, snapshot: RealtimeData) -> None:
        """Parse 주식체결 realtime data into snapshot fields."""
        try:
            price_str = self._api.get_comm_real_data(code, FID_CURRENT_PRICE)
            snapshot.current_price = int(price_str) if price_str else snapshot.current_price

            rate_str = self._api.get_comm_real_data(code, FID_CHANGE_RATE)
            snapshot.change_rate = float(rate_str) if rate_str else snapshot.change_rate

            vol_str = self._api.get_comm_real_data(code, FID_VOLUME)
            snapshot.volume = int(vol_str) if vol_str else snapshot.volume

            high_str = self._api.get_comm_real_data(code, FID_HIGH_PRICE)
            snapshot.high_price = abs(int(high_str)) if high_str else snapshot.high_price

            low_str = self._api.get_comm_real_data(code, FID_LOW_PRICE)
            snapshot.low_price = abs(int(low_str)) if low_str else snapshot.low_price

            open_str = self._api.get_comm_real_data(code, FID_OPEN_PRICE)
            snapshot.open_price = abs(int(open_str)) if open_str else snapshot.open_price

        except (ValueError, TypeError):
            logger.debug("Failed to parse tick data for code=%s", code)
