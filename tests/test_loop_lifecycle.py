"""Tests for trading-event-loop lifecycle: detach, callback removal, no double-apply."""
from __future__ import annotations

import random

from execution_engine.brokerage import FlatBrokerage
from execution_engine.engine import ExecutionEngine
from execution_engine.event_loop import TradingEventLoop
from execution_engine.orders import Order, OrderSide, OrderType
from portfolio.book import Portfolio
from portfolio.risk import RiskConfig, RiskManager
from strategy_engine.base import Signal, SignalType, Strategy


class _Noop(Strategy):
    name = "Noop"

    def on_tick(self, tick):
        return None


class _AlwaysBuyOnce(Strategy):
    name = "AlwaysBuyOnce"

    def __init__(self, symbols, quantity=1):
        super().__init__(symbols, quantity)
        self._sent = False

    def on_tick(self, tick):
        if self._sent:
            return None
        self._sent = True
        return Signal(
            type=SignalType.BUY,
            symbol=tick.symbol,
            quantity=self.quantity,
            price=tick.ltp,
            reason="test",
        )


def _make_setup(fake_feed, capital: float = 100_000.0):
    portfolio = Portfolio(initial_capital=capital)
    risk = RiskManager(portfolio, RiskConfig(max_capital_pct_per_trade=1.0))
    portfolio.on_trade(risk.on_trade)
    execution = ExecutionEngine(
        fake_feed, brokerage=FlatBrokerage(0), slippage_pct=0, latency_ms=0,
        rng=random.Random(0),
    )
    return portfolio, risk, execution


def test_detach_removes_loop_callbacks(fake_feed):
    portfolio, risk, execution = _make_setup(fake_feed)
    loop = TradingEventLoop(
        feed=fake_feed, strategy=_Noop(["INFY"]),
        execution=execution, portfolio=portfolio, risk=risk,
    )
    n_feed_before = len(fake_feed._callbacks)
    n_trade_before = len(execution._trade_listeners)
    loop.detach()
    assert len(fake_feed._callbacks) == n_feed_before - 1
    assert len(execution._trade_listeners) == n_trade_before - 1
    # Idempotent
    loop.detach()
    assert len(fake_feed._callbacks) == n_feed_before - 1


def test_stopped_loop_does_not_apply_trades(fake_feed):
    """A stopped event loop must not double-apply trades that are submitted
    directly to the execution engine after the loop's stop()."""
    portfolio, risk, execution = _make_setup(fake_feed)
    loop = TradingEventLoop(
        feed=fake_feed, strategy=_Noop(["INFY"]),
        execution=execution, portfolio=portfolio, risk=risk,
    )
    loop.start()
    fake_feed.push("INFY", 100.0)
    loop.stop()

    # Manually wire a single application path (mimics TradingApp's manual-fill listener).
    applied: list = []
    execution.on_trade(lambda trade, _order: applied.append(trade))

    fake_feed.push("INFY", 101.0)
    order = Order(
        symbol="INFY", side=OrderSide.BUY, quantity=1, order_type=OrderType.MARKET,
        strategy="MANUAL",
    )
    execution.submit(order)

    # Exactly one application: the test-installed listener. Loop's listener
    # is still in the list but must short-circuit while _running == False.
    assert len(applied) == 1
    pos = portfolio.position("INFY")
    # The loop's stale _on_trade did NOT apply (else position would be 1).
    assert pos is None or pos.quantity == 0


def test_set_strategy_detaches_old_loop(fake_feed, tmp_path, monkeypatch):
    """Switching strategies must not leave duplicate listeners behind."""
    monkeypatch.setattr("engine.create_feed", lambda *_a, **_kw: fake_feed)
    from engine import EngineConfig, TradingApp

    app = TradingApp(EngineConfig(
        initial_capital=100_000.0, slippage_pct=0.0, latency_ms=0,
        db_path=str(tmp_path / "swap.db"),
    ))
    app.set_strategy(_Noop(["INFY"]))
    feed_cb_count_after_first = len(app.feed._callbacks)

    # Swap to another strategy three times
    for _ in range(3):
        app.set_strategy(_Noop(["INFY"]))
    feed_cb_count_after_swaps = len(app.feed._callbacks)

    assert feed_cb_count_after_swaps == feed_cb_count_after_first, (
        f"Listener leak: {feed_cb_count_after_swaps} vs {feed_cb_count_after_first}"
    )


def test_strategy_swap_does_not_double_apply_trade(fake_feed, tmp_path, monkeypatch):
    """End-to-end: swap strategies twice, run one, fire a tick — trade applies once."""
    monkeypatch.setattr("engine.create_feed", lambda *_a, **_kw: fake_feed)
    from engine import EngineConfig, TradingApp

    app = TradingApp(EngineConfig(
        initial_capital=100_000.0, slippage_pct=0.0, latency_ms=0,
        db_path=str(tmp_path / "noleak.db"),
    ))
    app.set_strategy(_Noop(["INFY"]))
    app.set_strategy(_AlwaysBuyOnce(symbols=["INFY"], quantity=2))
    app.start()
    fake_feed.push("INFY", 1500.0)
    pos = app.portfolio.position("INFY")
    assert pos is not None
    assert pos.quantity == 2  # not 4 (would be 4 if double-applied)
    app.stop()


def test_remove_helpers_return_false_for_unknown_callback(fake_feed):
    portfolio, _risk, execution = _make_setup(fake_feed)

    def cb(_t, _o):
        return None

    assert execution.remove_on_trade(cb) is False
    assert fake_feed.remove_on_tick(cb) is False
    assert portfolio.remove_on_trade(cb) is False  # type: ignore[arg-type]
