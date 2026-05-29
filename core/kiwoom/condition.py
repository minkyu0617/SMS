# NOTE: Requires Windows + Kiwoom OpenAPI+ COM component.

from typing import Callable, Dict, List, Optional, Set

from utils.logger import get_logger

logger = get_logger(__name__)


class ConditionSearcher:
    """Manages Kiwoom condition search sessions and tracks candidate stocks."""

    SCREEN_BASE = 2000  # base screen number; incremented per condition

    def __init__(self, kiwoom_api) -> None:
        self._api = kiwoom_api
        self._conditions: Dict[int, str] = {}           # index -> name
        self._active_screens: Dict[str, str] = {}       # condition_name -> screen_no
        self._candidate_stocks: Dict[str, Set[str]] = {}  # condition_name -> {code}
        self._on_signal_callbacks: List[Callable[[str, str, str], None]] = []

        self._api.register_condition_callback(self._on_condition_event)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def load_conditions(self) -> Dict[int, str]:
        """Load condition list from Kiwoom API."""
        self._conditions = self._api.get_condition_list()
        logger.info("Loaded %d conditions: %s", len(self._conditions), self._conditions)
        return self._conditions

    def register_signal_callback(self, callback: Callable[[str, str, str], None]) -> None:
        """Register a callback(code, condition_name, kind) for condition signals."""
        self._on_signal_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start_condition(self, condition_name: str) -> bool:
        """Start realtime condition search by name. Returns True on success."""
        index = self._find_index(condition_name)
        if index is None:
            logger.error("Condition '%s' not found in loaded list.", condition_name)
            return False

        screen_no = str(self.SCREEN_BASE + index)
        result = self._api.send_condition(screen_no, condition_name, index, search_type=1)
        if result == 1:
            self._active_screens[condition_name] = screen_no
            if condition_name not in self._candidate_stocks:
                self._candidate_stocks[condition_name] = set()
            logger.info("Condition search started: '%s' on screen %s.", condition_name, screen_no)
            return True

        logger.error("Failed to start condition search '%s' (result=%d).", condition_name, result)
        return False

    def stop_condition(self, condition_name: str) -> None:
        """Stop an active realtime condition search."""
        screen_no = self._active_screens.pop(condition_name, None)
        if screen_no is None:
            logger.warning("Condition '%s' is not active.", condition_name)
            return

        index = self._find_index(condition_name)
        if index is not None:
            self._api.stop_condition(screen_no, condition_name, index)
        logger.info("Condition search stopped: '%s'.", condition_name)

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _on_condition_event(self, code: str, condition_name: str, kind: str) -> None:
        """Internal handler wired to KiwoomAPI condition callbacks."""
        self.on_condition_result(code, condition_name, kind)

    def on_condition_result(self, code: str, condition_name: str, kind: str) -> None:
        """Process a condition search signal.

        kind='I': stock entered condition -> add to candidates and fire callbacks.
        kind='D': stock exited condition  -> remove from candidates.
        """
        bucket = self._candidate_stocks.setdefault(condition_name, set())

        if kind == "I":
            if code not in bucket:
                bucket.add(code)
                logger.info("Condition '%s': code %s entered.", condition_name, code)
                for cb in self._on_signal_callbacks:
                    try:
                        cb(code, condition_name, kind)
                    except Exception:
                        logger.exception("Error in signal callback for code=%s", code)
        elif kind == "D":
            bucket.discard(code)
            logger.info("Condition '%s': code %s exited.", condition_name, code)
            for cb in self._on_signal_callbacks:
                try:
                    cb(code, condition_name, kind)
                except Exception:
                    logger.exception("Error in signal callback (exit) for code=%s", code)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_candidates(self, condition_name: Optional[str] = None) -> List[str]:
        """Return current candidate stocks for a condition (or all conditions)."""
        if condition_name is not None:
            return list(self._candidate_stocks.get(condition_name, set()))

        all_codes: Set[str] = set()
        for codes in self._candidate_stocks.values():
            all_codes.update(codes)
        return list(all_codes)

    def is_active(self, condition_name: str) -> bool:
        return condition_name in self._active_screens

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_index(self, condition_name: str) -> Optional[int]:
        for idx, name in self._conditions.items():
            if name == condition_name:
                return idx
        return None
