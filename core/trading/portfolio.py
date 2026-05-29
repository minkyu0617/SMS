from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Position:
    """Represents a single open stock position."""

    code: str
    name: str
    strategy_name: str
    total_quantity: int
    average_price: float
    current_price: float
    buy_steps_done: List[int] = field(default_factory=list)
    highest_price: float = 0.0
    entry_time: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if self.highest_price == 0.0:
            self.highest_price = self.current_price

    @property
    def profit_pct(self) -> float:
        """Current profit/loss percentage relative to average buy price."""
        if self.average_price <= 0:
            return 0.0
        return (self.current_price - self.average_price) / self.average_price * 100.0

    @property
    def profit_amount(self) -> float:
        return (self.current_price - self.average_price) * self.total_quantity

    @property
    def total_invested(self) -> float:
        return self.average_price * self.total_quantity

    @property
    def current_value(self) -> float:
        return self.current_price * self.total_quantity


class Portfolio:
    """Tracks all open positions."""

    def __init__(self) -> None:
        self._positions: Dict[str, Position] = {}

    def add_position(
        self,
        code: str,
        name: str,
        strategy_name: str,
        quantity: int,
        price: float,
    ) -> Position:
        """Create a new position or average-down an existing one."""
        if code in self._positions:
            return self._merge_position(code, quantity, price)

        position = Position(
            code=code,
            name=name,
            strategy_name=strategy_name,
            total_quantity=quantity,
            average_price=price,
            current_price=price,
            buy_steps_done=[1],
            highest_price=price,
        )
        self._positions[code] = position
        return position

    def _merge_position(self, code: str, qty: int, price: float) -> Position:
        pos = self._positions[code]
        total_cost = pos.average_price * pos.total_quantity + price * qty
        pos.total_quantity += qty
        pos.average_price = total_cost / pos.total_quantity
        return pos

    def update_position(self, code: str, current_price: float) -> Optional[Position]:
        pos = self._positions.get(code)
        if pos is None:
            return None
        pos.current_price = current_price
        if current_price > pos.highest_price:
            pos.highest_price = current_price
        return pos

    def mark_buy_step_done(self, code: str, step: int) -> None:
        pos = self._positions.get(code)
        if pos and step not in pos.buy_steps_done:
            pos.buy_steps_done.append(step)

    def remove_position(self, code: str) -> Optional[Position]:
        return self._positions.pop(code, None)

    def get_position(self, code: str) -> Optional[Position]:
        return self._positions.get(code)

    def get_all_positions(self) -> Dict[str, Position]:
        return dict(self._positions)

    def has_position(self, code: str) -> bool:
        return code in self._positions

    def total_invested(self) -> float:
        return sum(p.total_invested for p in self._positions.values())

    def total_current_value(self) -> float:
        return sum(p.current_value for p in self._positions.values())

    def total_profit_loss(self) -> float:
        return sum(p.profit_amount for p in self._positions.values())

    def total_profit_pct(self) -> float:
        invested = self.total_invested()
        if invested <= 0:
            return 0.0
        return self.total_profit_loss() / invested * 100.0

    def position_count(self) -> int:
        return len(self._positions)
