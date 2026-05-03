import numpy as np

from data_feed.base import Tick
from strategy_engine.base import SignalType
from strategy_engine.breakout import BreakoutStrategy
from strategy_engine.ema_crossover import EMACrossoverStrategy
from strategy_engine.rsi import RSIStrategy


def _feed_prices(strategy, symbol, prices):
    signals = []
    for p in prices:
        sig = strategy.on_tick(Tick(symbol=symbol, ltp=float(p)))
        if sig is not None:
            signals.append(sig)
    return signals


def test_rsi_buy_on_oversold_then_sell_on_overbought():
    s = RSIStrategy(symbols=["X"], period=14, oversold=30, overbought=70, quantity=1)
    crash = list(np.linspace(200, 50, 60))
    rally = list(np.linspace(50, 250, 60))
    signals = _feed_prices(s, "X", crash + rally)
    types = [sig.type for sig in signals]
    assert SignalType.BUY in types
    assert SignalType.SELL in types
    # Buy must come before sell.
    assert types.index(SignalType.BUY) < types.index(SignalType.SELL)


def test_ema_crossover_generates_buy():
    s = EMACrossoverStrategy(symbols=["X"], fast=5, slow=20, quantity=1)
    # Down-then-up scenario forces a crossover.
    prices = list(np.linspace(100, 60, 40)) + list(np.linspace(60, 200, 40))
    signals = _feed_prices(s, "X", prices)
    assert any(sig.type is SignalType.BUY for sig in signals)


def test_breakout_buy_above_channel():
    s = BreakoutStrategy(symbols=["X"], lookback=10, quantity=1)
    rangebound = [100 + (i % 5) for i in range(30)]
    breakout = [200, 205]
    signals = _feed_prices(s, "X", rangebound + breakout)
    assert any(sig.type is SignalType.BUY for sig in signals)


def test_strategy_requires_symbols():
    import pytest

    with pytest.raises(ValueError):
        RSIStrategy(symbols=[])


def test_ema_validates_periods():
    import pytest

    with pytest.raises(ValueError):
        EMACrossoverStrategy(symbols=["X"], fast=20, slow=10)
