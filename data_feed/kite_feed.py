"""Zerodha Kite Connect data feed adapter.

This is a thin adapter that hooks into the official `kiteconnect` Python
library when credentials are available. The implementation is fully optional
- if the library is missing or credentials are not set, we raise a clear
ImportError / RuntimeError when somebody tries to instantiate the feed.

Implementing the full WebSocket binary protocol is left to the official
KiteTicker; this adapter wires its callbacks into the engine's `Tick` model.
"""
from __future__ import annotations

import contextlib
from typing import Any

import pandas as pd

from data_feed.base import DataFeed, Tick
from utils.config import get_settings


class KiteDataFeed(DataFeed):
    def __init__(self) -> None:
        super().__init__()
        try:
            from kiteconnect import KiteConnect, KiteTicker  # type: ignore
        except ImportError as e:  # pragma: no cover - optional dep
            raise ImportError(
                "kiteconnect is not installed. `pip install kiteconnect` to use KiteDataFeed."
            ) from e

        settings = get_settings()
        if not (settings.kite_api_key and settings.kite_access_token):
            raise RuntimeError(
                "KITE_API_KEY and KITE_ACCESS_TOKEN must be set to use KiteDataFeed."
            )

        self._KiteConnect = KiteConnect
        self._KiteTicker = KiteTicker
        self._kite = KiteConnect(api_key=settings.kite_api_key)
        self._kite.set_access_token(settings.kite_access_token)
        self._ticker: Any | None = None
        self._token_to_symbol: dict[int, str] = {}
        self._symbol_to_token: dict[str, int] = {}

    def _resolve_token(self, symbol: str) -> int:
        if symbol in self._symbol_to_token:
            return self._symbol_to_token[symbol]
        instruments = self._kite.ltp([f"NSE:{symbol}"])
        token = int(instruments[f"NSE:{symbol}"]["instrument_token"])
        self._symbol_to_token[symbol] = token
        self._token_to_symbol[token] = symbol
        return token

    def start(self) -> None:  # pragma: no cover - requires creds
        if self._running:
            return
        settings = get_settings()
        self._ticker = self._KiteTicker(settings.kite_api_key, settings.kite_access_token)

        def on_ticks(_ws, ticks: list[dict[str, Any]]) -> None:
            for t in ticks:
                token = int(t.get("instrument_token", 0))
                symbol = self._token_to_symbol.get(token)
                if not symbol:
                    continue
                self._publish(
                    Tick(
                        symbol=symbol,
                        ltp=float(t.get("last_price", 0) or 0),
                        bid=t.get("depth", {}).get("buy", [{}])[0].get("price"),
                        ask=t.get("depth", {}).get("sell", [{}])[0].get("price"),
                        volume=t.get("volume_traded"),
                    )
                )

        def on_connect(ws, _response) -> None:
            tokens = [self._resolve_token(s) for s in self.symbols()]
            ws.subscribe(tokens)
            ws.set_mode(ws.MODE_FULL, tokens)

        self._ticker.on_ticks = on_ticks
        self._ticker.on_connect = on_connect
        self._ticker.connect(threaded=True)
        self._running = True

    def stop(self) -> None:  # pragma: no cover - requires creds
        if self._ticker is not None:
            with contextlib.suppress(Exception):
                self._ticker.close()
        self._running = False

    def get_history(self, symbol: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:  # pragma: no cover
        token = self._resolve_token(symbol)
        from datetime import datetime, timedelta

        days = int("".join(c for c in period if c.isdigit()) or 5)
        to = datetime.now()
        frm = to - timedelta(days=days)
        kite_interval = {"1m": "minute", "5m": "5minute", "15m": "15minute", "1d": "day"}.get(
            interval, "5minute"
        )
        candles = self._kite.historical_data(token, frm, to, kite_interval)
        df = pd.DataFrame(candles)
        if df.empty:
            return df
        df = df.rename(columns={"date": "timestamp"})
        df = df.set_index("timestamp")
        return df[["open", "high", "low", "close", "volume"]]
