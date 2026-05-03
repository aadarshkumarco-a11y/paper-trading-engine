"""Tests for the user-supplied strategy code loader."""
from __future__ import annotations

import pytest

from data_feed.base import Tick
from strategy_engine.code_loader import (
    CustomCodeStrategy,
    StrategyCodeError,
    load_strategy_class,
    validate_strategy_code,
)

VALID_DICT_STRATEGY = """
class Strategy:
    def __init__(self):
        self.flips = 0

    def on_tick(self, data):
        if data['price'] > 100:
            return 'BUY'
        return 'HOLD'
"""

VALID_SUBCLASS_STRATEGY = """
class Strategy(Strategy):
    name = "EmaCross"

    def on_tick(self, tick):
        if tick.ltp > 100:
            return Signal(type=SignalType.BUY, symbol=tick.symbol, quantity=1)
        return None
"""


def test_validate_accepts_simple_strategy():
    validate_strategy_code(VALID_DICT_STRATEGY)


def test_validate_rejects_empty_code():
    with pytest.raises(StrategyCodeError, match="empty"):
        validate_strategy_code("")


def test_validate_rejects_missing_strategy_class():
    code = "x = 1\ndef foo(): return 'BUY'\n"
    with pytest.raises(StrategyCodeError, match="No 'Strategy' class"):
        validate_strategy_code(code)


@pytest.mark.parametrize(
    "module",
    ["os", "subprocess", "socket", "ctypes", "shutil", "requests", "urllib", "threading"],
)
def test_validate_rejects_forbidden_imports(module):
    code = f"""
import {module}
class Strategy:
    def on_tick(self, data):
        return 'HOLD'
"""
    with pytest.raises(StrategyCodeError, match="not allowed"):
        validate_strategy_code(code)


def test_validate_rejects_from_imports_too():
    code = """
from os import system
class Strategy:
    def on_tick(self, data):
        return 'HOLD'
"""
    with pytest.raises(StrategyCodeError, match="not allowed"):
        validate_strategy_code(code)


@pytest.mark.parametrize("name", ["__import__", "eval", "exec", "compile", "open"])
def test_validate_rejects_dangerous_builtins(name):
    code = f"""
class Strategy:
    def on_tick(self, data):
        x = {name}
        return 'HOLD'
"""
    with pytest.raises(StrategyCodeError, match="not allowed"):
        validate_strategy_code(code)


def test_validate_rejects_dunder_attribute_access():
    code = """
class Strategy:
    def on_tick(self, data):
        cls = data.__class__
        return 'HOLD'
"""
    with pytest.raises(StrategyCodeError, match="dunder"):
        validate_strategy_code(code)


def test_validate_reports_syntax_error_with_line_number():
    code = "class Strategy:\n    def on_tick(self, data\n        return 'HOLD'\n"
    with pytest.raises(StrategyCodeError, match="SyntaxError"):
        validate_strategy_code(code)


def test_load_returns_callable_class():
    loaded = load_strategy_class(VALID_DICT_STRATEGY)
    inst = loaded.cls()
    assert inst.on_tick({"price": 200}) == "BUY"
    assert inst.on_tick({"price": 50}) == "HOLD"
    assert loaded.is_subclass is False


def test_custom_code_strategy_runs_dict_payload():
    loaded = load_strategy_class(VALID_DICT_STRATEGY)
    strat = CustomCodeStrategy(loaded, symbols=["DEMO"], quantity=5)
    sig = strat.on_tick(Tick(symbol="DEMO", ltp=120.0))
    assert sig is not None
    assert sig.type.value == "BUY"
    assert sig.symbol == "DEMO"
    assert sig.quantity == 5


def test_custom_code_strategy_suppresses_repeat_signals():
    loaded = load_strategy_class(VALID_DICT_STRATEGY)
    strat = CustomCodeStrategy(loaded, symbols=["DEMO"], quantity=1)
    first = strat.on_tick(Tick(symbol="DEMO", ltp=120.0))
    second = strat.on_tick(Tick(symbol="DEMO", ltp=120.5))
    assert first is not None
    assert second is None  # back-to-back BUY suppressed


def test_custom_code_strategy_swallows_runtime_errors():
    code = """
class Strategy:
    def on_tick(self, data):
        return 1 / 0
"""
    loaded = load_strategy_class(code)
    strat = CustomCodeStrategy(loaded, symbols=["DEMO"])
    sig = strat.on_tick(Tick(symbol="DEMO", ltp=100.0))
    assert sig is None
    assert strat.error_count == 1


def test_custom_code_strategy_supports_tuple_response():
    code = """
class Strategy:
    def on_tick(self, data):
        return ("BUY", 7)
"""
    loaded = load_strategy_class(code)
    strat = CustomCodeStrategy(loaded, symbols=["DEMO"], quantity=1)
    sig = strat.on_tick(Tick(symbol="DEMO", ltp=100.0))
    assert sig is not None
    assert sig.quantity == 7
