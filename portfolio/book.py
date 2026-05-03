"""In-memory portfolio with realized/unrealized PnL accounting."""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from execution_engine.orders import Trade
from portfolio.storage import PortfolioStorage
from utils.logger import get_logger


@dataclass
class Position:
    symbol: str
    quantity: int = 0  # signed: positive = long, negative = short
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    last_price: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.quantity != 0

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    @property
    def unrealized_pnl(self) -> float:
        if self.quantity == 0:
            return 0.0
        return (self.last_price - self.avg_price) * self.quantity

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_price": round(self.avg_price, 4),
            "last_price": round(self.last_price, 4),
            "market_value": round(self.market_value, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "realized_pnl": round(self.realized_pnl, 2),
        }


class Portfolio:
    """Cash + positions accounting. Thread-safe.

    Apply trades via `apply_trade(trade)` and update marks via `mark_to_market(symbol, price)`.
    """

    def __init__(
        self,
        initial_capital: float,
        storage: PortfolioStorage | None = None,
        session_id: int | None = None,
    ) -> None:
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.positions: dict[str, Position] = {}
        self.storage = storage
        self.session_id = session_id
        self.logger = get_logger("Portfolio")
        self._lock = threading.RLock()
        self._listeners: list[Callable[[Trade], None]] = []
        self._brokerage_paid = 0.0

    # ----- listeners -----
    def on_trade(self, callback: Callable[[Trade], None]) -> None:
        self._listeners.append(callback)

    # ----- mutation -----
    def apply_trade(self, trade: Trade) -> Position:
        with self._lock:
            pos = self.positions.setdefault(trade.symbol, Position(symbol=trade.symbol))
            signed_qty = trade.side.sign * trade.quantity
            new_qty = pos.quantity + signed_qty

            # Realised PnL for the closing portion (when sign flips or quantity reduces).
            if pos.quantity != 0 and (pos.quantity > 0) != (signed_qty > 0):
                closing_qty = min(abs(pos.quantity), abs(signed_qty))
                # PnL = (sell - buy) * qty for long; symmetric for short
                if pos.quantity > 0:  # closing long → selling
                    pos.realized_pnl += (trade.price - pos.avg_price) * closing_qty
                else:  # closing short → buying
                    pos.realized_pnl += (pos.avg_price - trade.price) * closing_qty

            if new_qty == 0:
                pos.quantity = 0
                pos.avg_price = 0.0
            elif (pos.quantity == 0) or (pos.quantity > 0) == (signed_qty > 0):
                # opening or adding to existing direction → weighted-avg price update
                total_cost = pos.avg_price * abs(pos.quantity) + trade.price * abs(signed_qty)
                pos.quantity = new_qty
                pos.avg_price = total_cost / abs(new_qty)
            else:
                # reducing existing position; avg_price unchanged for the remainder
                pos.quantity = new_qty
                if new_qty != 0 and (pos.quantity > 0) != (pos.quantity + signed_qty > 0):
                    # Position flipped through zero - reset avg to fill price for the residual
                    pos.avg_price = trade.price

            pos.last_price = trade.price
            self.cash += trade.cash_delta
            self._brokerage_paid += trade.brokerage

            self.logger.info(
                "Applied %s %s qty=%d @ %.4f → pos=%d avg=%.4f cash=%.2f realized=%.2f",
                trade.side.value, trade.symbol, trade.quantity, trade.price,
                pos.quantity, pos.avg_price, self.cash, pos.realized_pnl,
            )

        if self.storage is not None:
            self.storage.record_trade(self.session_id, trade)
            self.storage.record_equity_point(
                self.session_id,
                cash=self.cash,
                positions_value=self.positions_value(),
                equity=self.equity(),
            )
        for cb in list(self._listeners):
            try:
                cb(trade)
            except Exception:  # pragma: no cover
                self.logger.exception("Trade listener failed")
        return pos

    def mark_to_market(self, symbol: str, price: float) -> None:
        with self._lock:
            pos = self.positions.get(symbol)
            if pos is not None:
                pos.last_price = float(price)

    # ----- queries -----
    def positions_value(self) -> float:
        with self._lock:
            return sum(p.market_value for p in self.positions.values())

    def equity(self) -> float:
        with self._lock:
            return self.cash + self.positions_value()

    def realized_pnl(self) -> float:
        with self._lock:
            return sum(p.realized_pnl for p in self.positions.values())

    def unrealized_pnl(self) -> float:
        with self._lock:
            return sum(p.unrealized_pnl for p in self.positions.values())

    def total_pnl(self) -> float:
        return self.equity() - self.initial_capital

    def open_positions(self) -> list[Position]:
        with self._lock:
            return [p for p in self.positions.values() if p.is_open]

    def all_positions(self) -> list[Position]:
        with self._lock:
            return list(self.positions.values())

    def position(self, symbol: str) -> Position | None:
        with self._lock:
            return self.positions.get(symbol)

    @property
    def brokerage_paid(self) -> float:
        return self._brokerage_paid

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cash": round(self.cash, 2),
                "equity": round(self.equity(), 2),
                "positions_value": round(self.positions_value(), 2),
                "realized_pnl": round(self.realized_pnl(), 2),
                "unrealized_pnl": round(self.unrealized_pnl(), 2),
                "total_pnl": round(self.total_pnl(), 2),
                "brokerage_paid": round(self._brokerage_paid, 2),
                "open_positions": [p.to_dict() for p in self.open_positions()],
            }
