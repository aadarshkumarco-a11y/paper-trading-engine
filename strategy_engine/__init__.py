"""Strategy engine: base class, indicators and built-in strategies."""
from strategy_engine.base import Signal, SignalType, Strategy, StrategyContext
from strategy_engine.breakout import BreakoutStrategy
from strategy_engine.ema_crossover import EMACrossoverStrategy
from strategy_engine.indicators import atr, ema, rsi, sma
from strategy_engine.registry import build_strategy, register_strategy, registered_strategies
from strategy_engine.rsi import RSIStrategy

__all__ = [
    "Signal",
    "SignalType",
    "Strategy",
    "StrategyContext",
    "BreakoutStrategy",
    "EMACrossoverStrategy",
    "RSIStrategy",
    "atr",
    "ema",
    "rsi",
    "sma",
    "register_strategy",
    "registered_strategies",
    "build_strategy",
]
