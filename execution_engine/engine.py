"""Paper execution engine: simulates fills with slippage, brokerage and latency."""
from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable

from data_feed.base import DataFeed, Tick
from execution_engine.brokerage import BrokerageModel, ZerodhaEquityBrokerage
from execution_engine.orders import Order, OrderSide, OrderStatus, OrderType, Trade
from utils.logger import get_logger
from utils.market_hours import now_ist


class ExecutionEngine:
    """Simulates broker-side order matching for paper trading.

    - MARKET orders fill at `last_price * (1 ± slippage_pct)` after `latency_ms`.
    - LIMIT orders are filled when the next tick crosses the limit price.
    - Brokerage is added per fill via `BrokerageModel`.
    """

    def __init__(
        self,
        feed: DataFeed,
        brokerage: BrokerageModel | None = None,
        slippage_pct: float = 0.0005,
        latency_ms: int = 50,
        rng: random.Random | None = None,
    ) -> None:
        self.feed = feed
        self.brokerage = brokerage or ZerodhaEquityBrokerage()
        self.slippage_pct = float(slippage_pct)
        self.latency_ms = int(latency_ms)
        self.logger = get_logger("ExecutionEngine")
        self._rng = rng or random.Random()
        self._lock = threading.RLock()
        self._open_limit_orders: list[Order] = []
        self._trade_listeners: list[Callable[[Trade, Order], None]] = []
        self._reject_listeners: list[Callable[[Order], None]] = []
        feed.on_tick(self._on_tick_for_limit_orders)

    # ----- listeners -----
    def on_trade(self, callback: Callable[[Trade, Order], None]) -> None:
        self._trade_listeners.append(callback)

    def on_reject(self, callback: Callable[[Order], None]) -> None:
        self._reject_listeners.append(callback)

    def _emit_trade(self, trade: Trade, order: Order) -> None:
        for cb in list(self._trade_listeners):
            try:
                cb(trade, order)
            except Exception:  # pragma: no cover - defensive
                self.logger.exception("Trade listener failed")

    def _emit_reject(self, order: Order) -> None:
        for cb in list(self._reject_listeners):
            try:
                cb(order)
            except Exception:  # pragma: no cover - defensive
                self.logger.exception("Reject listener failed")

    # ----- public API -----
    def submit(self, order: Order) -> Order:
        self.logger.info(
            "Submit %s %s %s qty=%d type=%s",
            order.id, order.side.value, order.symbol, order.quantity, order.order_type.value,
        )
        last = self.feed.get_last_price(order.symbol)
        if last is None:
            return self._reject(order, "No live price for symbol")
        if order.order_type is OrderType.MARKET:
            self._sleep_latency()
            return self._fill(order, self._apply_slippage(last, order.side))
        # LIMIT order: check if it can fill immediately, otherwise queue.
        if self._can_fill_limit(order, last):
            return self._fill(order, order.limit_price)  # type: ignore[arg-type]
        with self._lock:
            self._open_limit_orders.append(order)
        return order

    def cancel(self, order_id: str) -> bool:
        with self._lock:
            for i, o in enumerate(self._open_limit_orders):
                if o.id == order_id:
                    o.status = OrderStatus.CANCELLED
                    self._open_limit_orders.pop(i)
                    return True
        return False

    def open_orders(self) -> list[Order]:
        with self._lock:
            return list(self._open_limit_orders)

    # ----- helpers -----
    def _on_tick_for_limit_orders(self, tick: Tick) -> None:
        with self._lock:
            still_open: list[Order] = []
            to_fill: list[Order] = []
            for o in self._open_limit_orders:
                if o.symbol != tick.symbol or o.status is not OrderStatus.PENDING:
                    still_open.append(o)
                    continue
                if self._can_fill_limit(o, tick.ltp):
                    to_fill.append(o)
                else:
                    still_open.append(o)
            self._open_limit_orders = still_open
        for o in to_fill:
            self._fill(o, o.limit_price)  # type: ignore[arg-type]

    @staticmethod
    def _can_fill_limit(order: Order, market_price: float) -> bool:
        if order.limit_price is None:
            return False
        if order.side is OrderSide.BUY:
            return market_price <= order.limit_price
        return market_price >= order.limit_price

    def _apply_slippage(self, price: float, side: OrderSide) -> float:
        # Random within [0, slippage_pct], adverse to the trader.
        slip = self._rng.random() * self.slippage_pct
        return price * (1 + slip * side.sign)

    def _sleep_latency(self) -> None:
        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

    def _fill(self, order: Order, price: float) -> Order:
        order.fill_price = float(price)
        order.filled_at = now_ist()
        order.status = OrderStatus.FILLED
        brokerage = self.brokerage.charge(order.side, order.quantity, price)
        trade = Trade(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=float(price),
            brokerage=float(brokerage),
            strategy=order.strategy,
        )
        self.logger.info(
            "Fill %s %s %s qty=%d @ %.4f brokerage=%.2f",
            order.id, order.side.value, order.symbol, order.quantity, price, brokerage,
        )
        self._emit_trade(trade, order)
        return order

    def _reject(self, order: Order, reason: str) -> Order:
        order.status = OrderStatus.REJECTED
        order.rejected_reason = reason
        self.logger.warning("Reject %s: %s", order.id, reason)
        self._emit_reject(order)
        return order
