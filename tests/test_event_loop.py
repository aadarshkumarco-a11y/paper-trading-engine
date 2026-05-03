"""End-to-end smoke test of the event loop using a fake feed."""
from __future__ import annotations

import random

from execution_engine.brokerage import FlatBrokerage
from execution_engine.engine import ExecutionEngine
from execution_engine.event_loop import TradingEventLoop
from portfolio.book import Portfolio
from portfolio.risk import RiskConfig, RiskManager
from strategy_engine.base import Signal, SignalType, Strategy


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


def test_event_loop_executes_signal_and_updates_portfolio(fake_feed):
    portfolio = Portfolio(initial_capital=100000.0)
    risk = RiskManager(portfolio, RiskConfig(max_capital_pct_per_trade=1.0))
    portfolio.on_trade(risk.on_trade)
    execution = ExecutionEngine(
        fake_feed, brokerage=FlatBrokerage(0), slippage_pct=0, latency_ms=0,
        rng=random.Random(0),
    )
    strategy = _AlwaysBuyOnce(symbols=["INFY"], quantity=2)
    loop = TradingEventLoop(
        feed=fake_feed,
        strategy=strategy,
        execution=execution,
        portfolio=portfolio,
        risk=risk,
    )
    loop.start()
    fake_feed.push("INFY", 1500.0)
    pos = portfolio.position("INFY")
    assert pos is not None and pos.quantity == 2
    assert portfolio.cash == 100000 - 3000
    loop.stop()


def test_event_loop_stop_loss_exit_fires(fake_feed):
    portfolio = Portfolio(initial_capital=100000.0)
    risk = RiskManager(portfolio, RiskConfig(stop_loss_pct=0.02, max_capital_pct_per_trade=1.0))
    portfolio.on_trade(risk.on_trade)
    execution = ExecutionEngine(
        fake_feed, brokerage=FlatBrokerage(0), slippage_pct=0, latency_ms=0,
        rng=random.Random(0),
    )
    strategy = _AlwaysBuyOnce(symbols=["INFY"], quantity=10)
    loop = TradingEventLoop(
        feed=fake_feed,
        strategy=strategy,
        execution=execution,
        portfolio=portfolio,
        risk=risk,
    )
    loop.start()
    fake_feed.push("INFY", 1000.0)
    assert portfolio.position("INFY").quantity == 10
    fake_feed.push("INFY", 970.0)  # -3%, beyond 2% SL
    assert portfolio.position("INFY").quantity == 0
    loop.stop()
