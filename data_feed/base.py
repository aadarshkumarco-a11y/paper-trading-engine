"""Abstract base classes for market data feeds."""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from utils.logger import get_logger
from utils.market_hours import now_ist


@dataclass
class Tick:
    symbol: str
    ltp: float
    timestamp: datetime = field(default_factory=now_ist)
    bid: float | None = None
    ask: float | None = None
    volume: int | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "ltp": self.ltp,
            "timestamp": self.timestamp.isoformat(),
            "bid": self.bid,
            "ask": self.ask,
            "volume": self.volume,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
        }


TickCallback = Callable[[Tick], None]


class DataFeed(ABC):
    """Common interface for live market data feeds.

    Implementations may push ticks via the registered callbacks
    (for true streaming feeds like WebSockets) or be polled with
    `get_last_price` / `get_history` (for REST/scraping fallbacks).
    """

    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)
        self._symbols: set[str] = set()
        self._callbacks: list[TickCallback] = []
        self._lock = threading.RLock()
        self._running = False
        self._last_ticks: dict[str, Tick] = {}

    # ----- subscription management -----
    def subscribe(self, symbols: Iterable[str]) -> None:
        with self._lock:
            for s in symbols:
                self._symbols.add(s)

    def unsubscribe(self, symbols: Iterable[str]) -> None:
        with self._lock:
            for s in symbols:
                self._symbols.discard(s)

    def symbols(self) -> list[str]:
        with self._lock:
            return sorted(self._symbols)

    def on_tick(self, callback: TickCallback) -> None:
        with self._lock:
            self._callbacks.append(callback)

    # ----- lifecycle -----
    @abstractmethod
    def start(self) -> None:
        """Start producing ticks (non-blocking)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the feed and release resources."""

    # ----- queries -----
    def get_last_price(self, symbol: str) -> float | None:
        with self._lock:
            tick = self._last_ticks.get(symbol)
        return tick.ltp if tick else None

    def get_last_tick(self, symbol: str) -> Tick | None:
        with self._lock:
            return self._last_ticks.get(symbol)

    @abstractmethod
    def get_history(self, symbol: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
        """Return OHLCV history with a DatetimeIndex (IST) and columns
        open, high, low, close, volume."""

    # ----- helpers -----
    def _publish(self, tick: Tick) -> None:
        with self._lock:
            self._last_ticks[tick.symbol] = tick
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb(tick)
            except Exception:  # pragma: no cover - defensive
                self.logger.exception("Tick callback failed")

    @property
    def is_running(self) -> bool:
        return self._running
