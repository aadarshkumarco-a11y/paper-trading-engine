"""Live-ish data feed using yfinance polling.

yfinance does not provide a true WebSocket, so this feed polls
the most recent quote at a configurable interval. It is sufficient
for paper trading at minute resolution and works without any
broker credentials.
"""
from __future__ import annotations

import threading
from collections.abc import Iterable
from datetime import datetime, timedelta

import pandas as pd

from data_feed.base import DataFeed, Tick
from utils.market_hours import IST


def _to_yahoo_symbol(symbol: str) -> str:
    """Normalize an NSE symbol for yfinance.

    - INFY -> INFY.NS
    - ^NSEI / NIFTY -> ^NSEI
    - ^NSEBANK / BANKNIFTY -> ^NSEBANK
    - already-suffixed symbols pass through.
    """
    s = symbol.strip().upper()
    aliases = {
        "NIFTY": "^NSEI",
        "NIFTY50": "^NSEI",
        "NIFTY 50": "^NSEI",
        "BANKNIFTY": "^NSEBANK",
        "NIFTYBANK": "^NSEBANK",
        "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
        "SENSEX": "^BSESN",
    }
    if s in aliases:
        return aliases[s]
    if s.startswith("^") or "." in s:
        return s
    return f"{s}.NS"


class YFinanceDataFeed(DataFeed):
    """Polls yfinance for the latest quote on each subscribed symbol."""

    def __init__(self, poll_interval: float = 5.0) -> None:
        super().__init__()
        self.poll_interval = max(1.0, float(poll_interval))
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, name="yfinance-feed", daemon=True)
        self._thread.start()
        self.logger.info("YFinance feed started (poll=%.1fs)", self.poll_interval)

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.logger.info("YFinance feed stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            symbols = self.symbols()
            if symbols:
                self._poll_once(symbols)
            self._stop_event.wait(self.poll_interval)

    def _poll_once(self, symbols: Iterable[str]) -> None:
        try:
            import yfinance as yf
        except ImportError:  # pragma: no cover
            self.logger.error("yfinance not installed")
            return
        ysyms = [_to_yahoo_symbol(s) for s in symbols]
        try:
            data = yf.download(
                tickers=ysyms,
                period="1d",
                interval="1m",
                progress=False,
                auto_adjust=False,
                threads=False,
            )
        except Exception:
            self.logger.exception("yfinance poll failed")
            return
        if data is None or data.empty:
            return
        for orig, ysym in zip(symbols, ysyms, strict=False):
            close = self._extract_last_close(data, ysym)
            if close is None:
                continue
            tick = Tick(symbol=orig, ltp=float(close))
            self._publish(tick)

    @staticmethod
    def _extract_last_close(df: pd.DataFrame, ysym: str) -> float | None:
        try:
            if isinstance(df.columns, pd.MultiIndex):
                if ("Close", ysym) in df.columns:
                    series = df[("Close", ysym)].dropna()
                else:
                    return None
            else:
                if "Close" in df.columns:
                    series = df["Close"].dropna()
                else:
                    return None
            if series.empty:
                return None
            return float(series.iloc[-1])
        except Exception:
            return None

    def get_history(self, symbol: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError:  # pragma: no cover
            return pd.DataFrame()
        ysym = _to_yahoo_symbol(symbol)
        try:
            df = yf.download(
                tickers=ysym,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                threads=False,
            )
        except Exception:
            self.logger.exception("yfinance history failed for %s", symbol)
            return pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [str(c).lower() for c in df.columns]
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(IST)
        keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
        return df[keep].dropna(how="all")

    def force_tick(self, symbol: str, price: float, ts: datetime | None = None) -> Tick:
        """Inject a synthetic tick (useful for tests and manual control)."""
        tick = Tick(symbol=symbol, ltp=price, timestamp=ts or datetime.now(IST))
        self._publish(tick)
        return tick

    def warm_up_from_history(self, symbol: str, period: str = "5d", interval: str = "5m") -> bool:
        """Seed the last_price cache so strategies can run before the first poll."""
        df = self.get_history(symbol, period=period, interval=interval)
        if df.empty:
            return False
        last_close = float(df["close"].iloc[-1])
        last_ts = df.index[-1].to_pydatetime()
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=IST)
        if datetime.now(IST) - last_ts > timedelta(days=10):  # pragma: no cover
            self.logger.warning("History for %s is stale: %s", symbol, last_ts)
        self._publish(Tick(symbol=symbol, ltp=last_close, timestamp=last_ts))
        return True
