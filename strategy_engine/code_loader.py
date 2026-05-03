"""Load user-supplied strategy code with lightweight validation.

This is a *paper trading* sandbox: we do reasonable AST-level validation to
catch obvious mistakes (forbidden imports, file IO, network) but we do NOT
attempt true Python sandboxing — RestrictedPython would be overkill for a
single-user paper trading dashboard. The user is implicitly running their
own code on their own machine; this module just protects against common
copy-pasted snippets that try to ``import os`` or ``open()`` files.
"""
from __future__ import annotations

import ast
import threading
import time
from dataclasses import dataclass
from typing import Any

from data_feed.base import Tick
from strategy_engine.base import Signal, SignalType, Strategy
from utils.logger import get_logger

logger = get_logger("CodeLoader")


class StrategyCodeError(Exception):
    """Raised when user-supplied strategy code is invalid or unsafe."""


# Modules that are clearly not needed by a trading strategy and have a high
# blast radius if a strategy author misuses them. The validator rejects any
# direct ``import`` / ``from ... import`` that touches these.
FORBIDDEN_IMPORTS = frozenset({
    "os", "sys", "subprocess", "shutil", "socket", "ctypes",
    "pickle", "marshal", "shelve", "importlib", "pty", "fcntl",
    "multiprocessing", "threading", "asyncio", "http", "urllib",
    "requests", "ftplib", "telnetlib", "smtplib",
})

# Names that point at the interpreter's escape hatches.
FORBIDDEN_NAMES = frozenset({
    "__import__", "eval", "exec", "compile", "open", "input",
    "globals", "vars", "memoryview",
})


def validate_strategy_code(code: str) -> ast.Module:
    """Parse + statically inspect user code. Raises StrategyCodeError on issue."""
    if not code or not code.strip():
        raise StrategyCodeError("Strategy code is empty.")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise StrategyCodeError(f"SyntaxError on line {exc.lineno}: {exc.msg}") from exc

    has_strategy_class = False

    for node in ast.walk(tree):
        # Block dangerous imports.
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in FORBIDDEN_IMPORTS:
                    raise StrategyCodeError(
                        f"Importing '{alias.name}' is not allowed in strategy code."
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".", 1)[0]
                if root in FORBIDDEN_IMPORTS:
                    raise StrategyCodeError(
                        f"Importing from '{node.module}' is not allowed in strategy code."
                    )
        # Block calls to forbidden builtins.
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise StrategyCodeError(
                f"Use of '{node.id}' is not allowed in strategy code."
            )
        # Block dunder attribute access (e.g. ``obj.__class__.__bases__``).
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            # Allow ``__init__`` since strategies legitimately define it.
            if node.attr not in {"__init__", "__name__", "__doc__"}:
                raise StrategyCodeError(
                    f"Access to dunder attribute '{node.attr}' is not allowed."
                )
        # Detect that the code defines a class named ``Strategy`` (or that
        # subclasses Strategy).
        elif isinstance(node, ast.ClassDef):
            if node.name == "Strategy":
                has_strategy_class = True
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "Strategy":
                    has_strategy_class = True

    if not has_strategy_class:
        raise StrategyCodeError(
            "No 'Strategy' class found. Define `class Strategy:` with an "
            "`on_tick(self, data)` method."
        )

    return tree


def _build_safe_namespace() -> dict[str, Any]:
    """Build a globals dict the user code is exec'd into.

    Intentionally minimal: the user gets pandas / numpy / math, the project's
    `Tick`, `Signal`, `SignalType`, and the `Strategy` base class, plus a
    curated set of safe builtins. No file IO, no network, no introspection
    helpers.
    """
    import builtins as _b
    import math

    import numpy as np
    import pandas as pd

    safe_builtins = {
        # Iteration / containers
        "len": len, "range": range, "enumerate": enumerate, "zip": zip,
        "map": map, "filter": filter, "sorted": sorted, "reversed": reversed,
        "list": list, "tuple": tuple, "dict": dict, "set": set, "frozenset": frozenset,
        # Numeric
        "abs": abs, "min": min, "max": max, "sum": sum, "round": round,
        "int": int, "float": float, "bool": bool, "str": str, "bytes": bytes,
        # Type checks
        "isinstance": isinstance, "issubclass": issubclass, "type": type,
        # Misc
        "print": print, "any": any, "all": all, "iter": iter, "next": next,
        "True": True, "False": False, "None": None,
        "Exception": Exception, "ValueError": ValueError, "KeyError": KeyError,
        "TypeError": TypeError, "ZeroDivisionError": ZeroDivisionError,
        "ArithmeticError": ArithmeticError,
        "getattr": getattr, "setattr": setattr, "hasattr": hasattr, "callable": callable,
        # Required for `class X:` syntax to work at exec time:
        "__build_class__": _b.__build_class__,
        "__name__": "__user_strategy__",
    }

    return {
        "__builtins__": safe_builtins,
        "pd": pd, "np": np, "math": math,
        "Strategy": Strategy,
        "Signal": Signal,
        "SignalType": SignalType,
        "Tick": Tick,
        "BUY": "BUY", "SELL": "SELL", "HOLD": "HOLD", "EXIT": "EXIT",
    }


@dataclass
class LoadedStrategy:
    cls: type
    is_subclass: bool


def load_strategy_class(code: str) -> LoadedStrategy:
    """Validate and exec user code, returning the class to instantiate."""
    validate_strategy_code(code)
    namespace = _build_safe_namespace()
    try:
        compiled = compile(code, "<user-strategy>", "exec")
        exec(compiled, namespace)  # noqa: S102 - validated above
    except StrategyCodeError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise StrategyCodeError(f"Strategy code failed to load: {exc}") from exc

    cls = namespace.get("Strategy")
    if cls is None or not isinstance(cls, type):
        raise StrategyCodeError("`Strategy` symbol is not a class.")

    is_subclass = False
    try:
        is_subclass = issubclass(cls, Strategy)
    except TypeError:
        is_subclass = False
    return LoadedStrategy(cls=cls, is_subclass=is_subclass)


class CustomCodeStrategy(Strategy):
    """Adapter that wraps a user-supplied class into the engine's Strategy API.

    Accepts both shapes:
      1. ``class Strategy(Strategy):`` — proper subclass; we instantiate with
         (symbols, quantity) and delegate `on_tick(tick)`.
      2. ``class Strategy:`` (zero-arg, dict-based) — author's `on_tick(self, data)`
         expects a dict like ``{"symbol", "price", "ema", "rsi", ...}``;
         return value can be ``"BUY" / "SELL" / "HOLD" / Signal`` or a tuple
         ``("BUY", quantity)``.

    Either way the engine sees a normal Strategy and gets back Signal | None.
    """

    name = "CustomCode"

    def __init__(
        self,
        loaded: LoadedStrategy,
        symbols: list[str],
        quantity: int = 1,
        on_tick_timeout_s: float = 1.0,
    ) -> None:
        super().__init__(symbols=symbols, quantity=quantity)
        self._loaded = loaded
        self._on_tick_timeout_s = float(on_tick_timeout_s)
        self._last_signal_per_symbol: dict[str, SignalType] = {}
        self._error_count = 0
        self._error_lock = threading.Lock()

        if loaded.is_subclass:
            self._inner = loaded.cls(symbols=symbols, quantity=quantity)
        else:
            try:
                self._inner = loaded.cls()
            except TypeError:
                # Some authors define __init__(self, symbols=...).
                self._inner = loaded.cls(symbols=symbols)

    @property
    def error_count(self) -> int:
        return self._error_count

    def on_tick(self, tick: Tick) -> Signal | None:
        self.context.update(tick)
        try:
            t0 = time.monotonic()
            if self._loaded.is_subclass:
                result = self._inner.on_tick(tick)
            else:
                payload = self._build_dict_payload(tick)
                result = self._inner.on_tick(payload)
            elapsed = time.monotonic() - t0
            if elapsed > self._on_tick_timeout_s:
                logger.warning(
                    "Custom strategy on_tick took %.2fs (>%.2fs threshold)",
                    elapsed, self._on_tick_timeout_s,
                )
        except Exception as exc:
            with self._error_lock:
                self._error_count += 1
            logger.exception("Custom strategy on_tick raised: %s", exc)
            return None

        return self._coerce_signal(result, tick)

    def _build_dict_payload(self, tick: Tick) -> dict[str, Any]:
        closes = self.context.closes(tick.symbol)
        ema_short = closes.ewm(span=9, adjust=False).mean().iloc[-1] if len(closes) else float(tick.ltp)
        ema_long = closes.ewm(span=21, adjust=False).mean().iloc[-1] if len(closes) else float(tick.ltp)
        return {
            "symbol": tick.symbol,
            "price": float(tick.ltp),
            "ltp": float(tick.ltp),
            "high": float(tick.high) if tick.high is not None else float(tick.ltp),
            "low": float(tick.low) if tick.low is not None else float(tick.ltp),
            "volume": int(tick.volume or 0),
            "timestamp": tick.timestamp,
            "ema": float(ema_short),
            "ema_short": float(ema_short),
            "ema_long": float(ema_long),
            "history": list(closes),
        }

    def _coerce_signal(self, raw: Any, tick: Tick) -> Signal | None:
        if raw is None:
            return None
        signal_type: SignalType
        qty = self.quantity
        if isinstance(raw, Signal):
            return raw
        if isinstance(raw, SignalType):
            signal_type = raw
        elif isinstance(raw, str):
            normalized = raw.strip().upper()
            if normalized in {"BUY", "SELL", "HOLD", "EXIT"}:
                signal_type = SignalType(normalized)
            else:
                return None
        elif isinstance(raw, tuple) and len(raw) == 2:
            head = raw[0]
            if isinstance(head, str) and head.upper() in {"BUY", "SELL", "HOLD", "EXIT"}:
                signal_type = SignalType(head.upper())
                try:
                    qty = max(1, int(raw[1]))
                except (TypeError, ValueError):
                    qty = self.quantity
            else:
                return None
        else:
            return None

        if signal_type is SignalType.HOLD:
            return None

        # Suppress duplicate consecutive BUY/SELL signals on the same symbol so
        # a careless user strategy that always returns "BUY" doesn't blast the
        # engine with orders every tick.
        last = self._last_signal_per_symbol.get(tick.symbol)
        if last == signal_type and signal_type in (SignalType.BUY, SignalType.SELL):
            return None
        self._last_signal_per_symbol[tick.symbol] = signal_type

        return Signal(
            type=signal_type,
            symbol=tick.symbol,
            quantity=qty,
            price=float(tick.ltp),
            reason="custom-code",
        )
