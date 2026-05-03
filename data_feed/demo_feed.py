"""Deterministic in-memory data feed for offline UI demos and integration tests.

Useful when:
- The Indian market is closed (yfinance returns no data outside 09:15-15:30 IST).
- You want a reproducible price stream for screen recordings or smoke tests.

The feed cycles through a hard-coded V-shaped price path
(200 → 50 → 250) for every subscribed symbol, which is enough to drive
the bundled RSI / EMA-crossover / Breakout strategies through full
buy → exit cycles within ~30 seconds.
"""
from __future__ import annotations

import threading
from collections.abc import Sequence

import pandas as pd

from data_feed.base import DataFeed, Tick
from utils.market_hours import IST


def _v_shaped_path() -> list[float]:
    """Build a deterministic 'flat → drop → rally' price path.

    Shape:
      - 20 flat ticks at 200 to warm up indicators with no crossover,
      - 12 ticks gently drifting 200 → 175 (fast EMA crosses *below* slow),
      - 6 ticks consolidating around 174–176,
      - 30 ticks rallying 175 → 240 (fast EMA crosses *back above* slow,
        triggering BUY; then a smooth uptrend so the long position can
        ride the trend to a +4 % take-profit).
    """
    flat = [200.0] * 20
    drop_steps = 12
    drop = [200.0 - 25.0 * i / drop_steps for i in range(1, drop_steps + 1)]  # 200→175
    consol = [174.0, 175.0, 176.0, 175.0, 174.5, 175.0]
    rally_steps = 30
    rally = [175.0 + (240.0 - 175.0) * i / rally_steps for i in range(1, rally_steps + 1)]
    return flat + drop + consol + rally


class DemoDataFeed(DataFeed):
    """Emits a scripted, deterministic V-shaped price stream per symbol.

    Each subscribed symbol gets the same shape (independent index), so RSI
    will always trigger BUY near the trough and SELL near the peak.
    """

    def __init__(
        self,
        tick_interval: float = 0.5,
        path: Sequence[float] | None = None,
    ) -> None:
        super().__init__()
        self.tick_interval = max(0.05, float(tick_interval))
        self.path = list(path) if path is not None else _v_shaped_path()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._idx_per_symbol: dict[str, int] = {}

    def start(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, name="demo-feed", daemon=True)
        self._thread.start()
        self.logger.info(
            "DemoDataFeed started (interval=%.2fs, %d ticks/symbol)",
            self.tick_interval, len(self.path),
        )

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.logger.info("DemoDataFeed stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            for sym in self.symbols():
                idx = self._idx_per_symbol.get(sym, 0)
                if idx >= len(self.path):
                    continue
                price = float(self.path[idx])
                self._idx_per_symbol[sym] = idx + 1
                self._publish(Tick(symbol=sym, ltp=price))
            self._stop_event.wait(self.tick_interval)

    def get_history(self, symbol: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
        # No real history — return empty so warm_up is a no-op.
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"]).astype(
            {"open": float, "high": float, "low": float, "close": float, "volume": float}
        ).pipe(lambda d: d.set_index(pd.DatetimeIndex([], tz=IST, name="timestamp")))
