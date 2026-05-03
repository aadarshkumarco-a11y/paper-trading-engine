"""Lightweight strategy registry so the UI can list and instantiate strategies."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from strategy_engine.base import Strategy

_REGISTRY: dict[str, type[Strategy]] = {}


def register_strategy(name: str | None = None) -> Callable[[type[Strategy]], type[Strategy]]:
    def decorator(cls: type[Strategy]) -> type[Strategy]:
        key = name or cls.name or cls.__name__
        _REGISTRY[key] = cls
        return cls

    return decorator


def registered_strategies() -> dict[str, type[Strategy]]:
    return dict(_REGISTRY)


def build_strategy(name: str, **kwargs: Any) -> Strategy:
    if name not in _REGISTRY:
        raise KeyError(f"Strategy '{name}' is not registered. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name](**kwargs)


# Register the built-in strategies.
def _register_builtins() -> None:
    from strategy_engine.breakout import BreakoutStrategy
    from strategy_engine.ema_crossover import EMACrossoverStrategy
    from strategy_engine.rsi import RSIStrategy

    _REGISTRY.setdefault("RSI", RSIStrategy)
    _REGISTRY.setdefault("EMA Crossover", EMACrossoverStrategy)
    _REGISTRY.setdefault("Breakout", BreakoutStrategy)


_register_builtins()
