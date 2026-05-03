"""Strategy base class and signal model."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import pandas as pd

from data_feed.base import Tick
from utils.market_hours import now_ist


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    EXIT = "EXIT"


@dataclass
class Signal:
    type: SignalType
    symbol: str
    quantity: int = 1
    price: float | None = None
    reason: str = ""
    timestamp: datetime = field(default_factory=now_ist)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        return self.type in (SignalType.BUY, SignalType.SELL, SignalType.EXIT)


@dataclass
class StrategyContext:
    """Per-symbol rolling buffers and metadata available to strategies."""

    history_per_symbol: int = 500

    def __post_init__(self) -> None:
        self._closes: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self.history_per_symbol)
        )
        self._highs: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self.history_per_symbol)
        )
        self._lows: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self.history_per_symbol)
        )
        self._timestamps: dict[str, deque[datetime]] = defaultdict(
            lambda: deque(maxlen=self.history_per_symbol)
        )

    def update(self, tick: Tick) -> None:
        s = tick.symbol
        self._closes[s].append(float(tick.ltp))
        self._highs[s].append(float(tick.high if tick.high is not None else tick.ltp))
        self._lows[s].append(float(tick.low if tick.low is not None else tick.ltp))
        self._timestamps[s].append(tick.timestamp)

    def seed_history(self, symbol: str, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        for col_target, col_source in (
            (self._closes[symbol], "close"),
            (self._highs[symbol], "high"),
            (self._lows[symbol], "low"),
        ):
            if col_source in df.columns:
                col_target.extend(float(v) for v in df[col_source].dropna().tolist())
        self._timestamps[symbol].extend(df.index.to_pydatetime().tolist())

    def closes(self, symbol: str) -> pd.Series:
        return pd.Series(list(self._closes.get(symbol, [])))

    def highs(self, symbol: str) -> pd.Series:
        return pd.Series(list(self._highs.get(symbol, [])))

    def lows(self, symbol: str) -> pd.Series:
        return pd.Series(list(self._lows.get(symbol, [])))

    def __len__(self) -> int:  # number of tracked symbols
        return len(self._closes)


class Strategy(ABC):
    """User-facing base class for trading strategies.

    Implementations must define `on_tick` and may override `warm_up` to
    pre-populate the context with historical bars before live trading begins.
    """

    name: str = "Strategy"

    def __init__(self, symbols: list[str], quantity: int = 1) -> None:
        if not symbols:
            raise ValueError("Strategy requires at least one symbol")
        self.symbols = list(symbols)
        self.quantity = int(quantity)
        self.context = StrategyContext()

    def warm_up(self, history_loader) -> None:
        """Optional: pre-fill context with bars. `history_loader(symbol)` returns DataFrame."""
        for sym in self.symbols:
            df = history_loader(sym)
            self.context.seed_history(sym, df)

    @abstractmethod
    def on_tick(self, tick: Tick) -> Signal | None:
        """Return a Signal or None. Called for every published tick."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} symbols={self.symbols} qty={self.quantity}>"
