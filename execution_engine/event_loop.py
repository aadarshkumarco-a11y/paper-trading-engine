"""Trading event loop: ties feed → strategy → risk → execution → portfolio."""
from __future__ import annotations

import threading

from data_feed.base import DataFeed, Tick
from execution_engine.engine import ExecutionEngine
from execution_engine.orders import Order, OrderSide, OrderType, Trade
from portfolio.book import Portfolio
from portfolio.risk import RiskManager
from strategy_engine.base import Signal, SignalType, Strategy
from utils.logger import get_logger
from utils.market_hours import is_market_open


class TradingEventLoop:
    """Connects the moving parts and runs the live event loop.

    The actual loop runs inside the data feed's thread (callback-driven), so
    `start()` only needs to subscribe symbols and start the feed.
    """

    def __init__(
        self,
        feed: DataFeed,
        strategy: Strategy,
        execution: ExecutionEngine,
        portfolio: Portfolio,
        risk: RiskManager | None = None,
        respect_market_hours: bool = False,
    ) -> None:
        self.feed = feed
        self.strategy = strategy
        self.execution = execution
        self.portfolio = portfolio
        self.risk = risk
        self.respect_market_hours = bool(respect_market_hours)
        self.logger = get_logger("EventLoop")
        self._running = False
        self._detached = False
        self._lock = threading.RLock()

        # Wire callbacks. Track them so detach() can remove the *exact* same
        # function objects later without dropping listeners that other
        # subsystems registered.
        self.feed.on_tick(self._on_tick)
        self.execution.on_trade(self._on_trade)
        if self.risk is not None:
            self.portfolio.on_trade(self.risk.on_trade)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self.feed.subscribe(self.strategy.symbols)
            try:
                self.strategy.warm_up(self._history_loader)
            except Exception:
                self.logger.exception("Strategy warm-up failed")
            self.feed.start()
            self._running = True
            self.logger.info("Event loop started")

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self.feed.stop()
            self._running = False
            self.logger.info("Event loop stopped")

    def detach(self) -> None:
        """Remove this loop's callbacks from the feed/execution/portfolio.

        Safe to call multiple times. Required when the loop is being replaced
        by a new one (e.g. swapping strategies in TradingApp.set_strategy())
        — without it, stale callbacks from previous loops would keep firing
        and apply trades multiple times to the portfolio.
        """
        with self._lock:
            if self._detached:
                return
            self._detached = True
            try:
                self.feed.remove_on_tick(self._on_tick)
            except Exception:  # pragma: no cover - defensive
                self.logger.exception("Failed to detach feed callback")
            try:
                self.execution.remove_on_trade(self._on_trade)
            except Exception:  # pragma: no cover - defensive
                self.logger.exception("Failed to detach trade listener")
            if self.risk is not None:
                try:
                    self.portfolio.remove_on_trade(self.risk.on_trade)
                except Exception:  # pragma: no cover - defensive
                    self.logger.exception("Failed to detach risk listener")

    # ----- internals -----
    def _history_loader(self, symbol: str):
        try:
            return self.feed.get_history(symbol, period="5d", interval="5m")
        except Exception:
            self.logger.exception("History load failed for %s", symbol)
            import pandas as pd

            return pd.DataFrame()

    def _on_tick(self, tick: Tick) -> None:
        # Defensive guard: a stopped (or detached) loop must not run the
        # strategy or generate trades, even if the feed still holds a stale
        # reference to this callback.
        if self._detached or not self._running:
            return
        try:
            if self.respect_market_hours and not is_market_open(tick.timestamp):
                return
            self.portfolio.mark_to_market(tick.symbol, tick.ltp)

            # Risk-driven exits first.
            if self.risk is not None:
                exit_signal = self.risk.check_exits(tick.symbol, tick.ltp)
                if exit_signal is not None:
                    self._handle_signal(exit_signal, tick)

            signal = self.strategy.on_tick(tick)
            if signal is not None and signal.is_actionable:
                self._handle_signal(signal, tick)
        except Exception:
            self.logger.exception("Tick handler failed")

    def _handle_signal(self, signal: Signal, tick: Tick) -> None:
        last_price = tick.ltp
        if self.risk is not None:
            decision = self.risk.evaluate_signal(signal, last_price)
            if not decision.allow:
                self.logger.info("Signal rejected: %s", decision.reason)
                return
            qty = decision.quantity
        else:
            qty = signal.quantity

        side = OrderSide.SELL if signal.type in (SignalType.SELL, SignalType.EXIT) else OrderSide.BUY
        order = Order(
            symbol=signal.symbol,
            side=side,
            quantity=qty,
            order_type=OrderType.MARKET,
            strategy=type(self.strategy).__name__,
            metadata={"reason": signal.reason, **signal.metadata},
        )
        self.execution.submit(order)

    def _on_trade(self, trade: Trade, _order: Order) -> None:
        # When the loop is stopped or detached, the TradingApp's manual-fill
        # listener owns trade application. Skip here to avoid double-applying
        # the same trade to the portfolio.
        if self._detached or not self._running:
            return
        self.portfolio.apply_trade(trade)
