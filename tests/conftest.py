"""Shared test fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from data_feed.base import DataFeed, Tick  # noqa: E402


class FakeDataFeed(DataFeed):
    """Manual data feed: tests publish ticks directly."""

    def __init__(self) -> None:
        super().__init__()

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def get_history(self, symbol: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
        return pd.DataFrame()

    def push(self, symbol: str, price: float, **kwargs) -> Tick:
        tick = Tick(symbol=symbol, ltp=float(price), **kwargs)
        self._publish(tick)
        return tick


@pytest.fixture
def fake_feed() -> FakeDataFeed:
    return FakeDataFeed()


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test.db"
