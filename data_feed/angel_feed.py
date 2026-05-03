"""Angel One SmartAPI live data feed.

This adapter wires the official `smartapi-python` library
(https://github.com/angel-one/smartapi-python) into the engine's
DataFeed interface.

- Login with `SmartConnect.generateSession(client_code, password, totp)`,
  where the TOTP is generated from `ANGEL_TOTP_SECRET` via pyotp.
- Live ticks via `SmartWebSocketV2` in mode=1 (LTP).
- Historical OHLCV via `getCandleData`.

The library is an *optional* dependency. Importing this module without
`smartapi-python` installed is fine; instantiating `AngelDataFeed`
raises a helpful ImportError instead.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

import pandas as pd

from data_feed.angel_symbol_master import AngelSymbolMaster
from data_feed.base import DataFeed, Tick
from utils.config import get_settings
from utils.market_hours import IST


class AngelDataFeed(DataFeed):
    INTERVAL_MAP = {
        "1m": "ONE_MINUTE",
        "3m": "THREE_MINUTE",
        "5m": "FIVE_MINUTE",
        "10m": "TEN_MINUTE",
        "15m": "FIFTEEN_MINUTE",
        "30m": "THIRTY_MINUTE",
        "1h": "ONE_HOUR",
        "1d": "ONE_DAY",
    }
    LTP_MODE = 1
    QUOTE_MODE = 2

    def __init__(
        self,
        exchange: str = "NSE",
        mode: int = LTP_MODE,
        symbol_master: AngelSymbolMaster | None = None,
    ) -> None:
        super().__init__()
        try:
            from SmartApi import SmartConnect  # type: ignore
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2  # type: ignore
        except ImportError as e:  # pragma: no cover - optional dep
            raise ImportError(
                "smartapi-python is not installed. Install it with:\n"
                "    pip install smartapi-python pyotp\n"
                "See https://github.com/angel-one/smartapi-python"
            ) from e

        try:
            import pyotp  # type: ignore
        except ImportError as e:  # pragma: no cover - optional dep
            raise ImportError("pyotp is required for Angel SmartAPI TOTP login") from e

        settings = get_settings()
        if not (settings.angel_api_key and settings.angel_client_code and settings.angel_password):
            raise RuntimeError(
                "ANGEL_API_KEY, ANGEL_CLIENT_CODE and ANGEL_PASSWORD must be set."
            )
        if not settings.angel_totp_secret:
            raise RuntimeError(
                "ANGEL_TOTP_SECRET (your authenticator-app QR value) is required for login."
            )

        self._SmartConnect = SmartConnect
        self._SmartWebSocketV2 = SmartWebSocketV2
        self._pyotp = pyotp
        self._settings = settings
        self.exchange = exchange.upper()
        self.mode = int(mode)
        self.symbol_master = symbol_master or AngelSymbolMaster()

        self._client = None  # SmartConnect instance after login
        self._ws = None  # SmartWebSocketV2 instance
        self._ws_thread: threading.Thread | None = None
        self._auth_token: str | None = None
        self._feed_token: str | None = None
        self._symbol_to_token: dict[str, str] = {}
        self._token_to_symbol: dict[str, str] = {}
        self._correlation_id = "paper-trading-engine"

    # ----- public API -----
    def login(self) -> None:
        """Generate the SmartAPI session (idempotent)."""
        if self._auth_token:
            return
        client = self._SmartConnect(api_key=self._settings.angel_api_key)
        totp = self._pyotp.TOTP(self._settings.angel_totp_secret).now()
        data = client.generateSession(
            self._settings.angel_client_code, self._settings.angel_password, totp
        )
        if not data or not data.get("status"):
            raise RuntimeError(f"Angel login failed: {data}")
        body = data.get("data", {})
        self._auth_token = body.get("jwtToken")
        feed_token = body.get("feedToken") or client.getfeedToken()
        self._feed_token = feed_token
        self._client = client
        self.logger.info("Angel SmartAPI login OK; feed token acquired")

    def start(self) -> None:
        if self._running:
            return
        self.login()
        self._resolve_symbol_tokens()
        self._connect_websocket()
        self._running = True
        self.logger.info("AngelDataFeed started for %d symbols", len(self._symbol_to_token))

    def stop(self) -> None:
        self._running = False
        if self._ws is not None:
            try:
                self._ws.close_connection()
            except Exception:  # pragma: no cover - defensive
                self.logger.exception("Failed to close Angel WebSocket")
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=2)
        self.logger.info("AngelDataFeed stopped")

    def get_history(self, symbol: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
        if self._client is None:
            self.login()
        token = self._token_for(symbol)
        if token is None:
            self.logger.warning("Unknown symbol %s on %s", symbol, self.exchange)
            return pd.DataFrame()
        days = int("".join(c for c in period if c.isdigit()) or "5")
        to = datetime.now()
        frm = to - timedelta(days=days)
        params = {
            "exchange": self.exchange,
            "symboltoken": token,
            "interval": self.INTERVAL_MAP.get(interval, "FIVE_MINUTE"),
            "fromdate": frm.strftime("%Y-%m-%d %H:%M"),
            "todate": to.strftime("%Y-%m-%d %H:%M"),
        }
        try:
            resp = self._client.getCandleData(params)  # type: ignore[union-attr]
        except Exception:
            self.logger.exception("Angel history fetch failed for %s", symbol)
            return pd.DataFrame()
        rows = resp.get("data") if isinstance(resp, dict) else None
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True).dt.tz_convert(IST)
        df = df.set_index("timestamp")
        return df[["open", "high", "low", "close", "volume"]]

    # ----- internal helpers -----
    def _token_for(self, symbol: str) -> str | None:
        if symbol in self._symbol_to_token:
            return self._symbol_to_token[symbol]
        token = self.symbol_master.token_for(symbol, exchange=self.exchange)
        if token:
            self._symbol_to_token[symbol] = token
            self._token_to_symbol[str(token)] = symbol
        return token

    def _resolve_symbol_tokens(self) -> None:
        for sym in self.symbols():
            self._token_for(sym)

    def _build_token_list(self) -> list[dict]:
        ex_type = self.symbol_master.exchange_type(self.exchange)
        tokens = list({str(t) for t in self._symbol_to_token.values()})
        if not tokens:
            return []
        return [{"exchangeType": ex_type, "tokens": tokens}]

    def _connect_websocket(self) -> None:  # pragma: no cover - requires creds
        ws = self._SmartWebSocketV2(
            self._auth_token,
            self._settings.angel_api_key,
            self._settings.angel_client_code,
            self._feed_token,
        )

        def on_open(_wsapp) -> None:
            ws.subscribe(self._correlation_id, self.mode, self._build_token_list())

        def on_data(_wsapp, message) -> None:
            try:
                self._handle_ws_message(message)
            except Exception:
                self.logger.exception("Failed to process Angel tick")

        def on_error(_wsapp, error) -> None:
            self.logger.error("Angel WS error: %s", error)

        def on_close(_wsapp) -> None:
            self.logger.info("Angel WS closed")

        ws.on_open = on_open
        ws.on_data = on_data
        ws.on_error = on_error
        ws.on_close = on_close
        self._ws = ws

        def runner() -> None:
            try:
                ws.connect()
            except Exception:
                self.logger.exception("Angel WS connect failed")

        self._ws_thread = threading.Thread(target=runner, name="angel-ws", daemon=True)
        self._ws_thread.start()
        # Give the socket a moment to open before the first publish.
        time.sleep(0.5)

    def _handle_ws_message(self, message) -> None:
        # Angel WSV2 may deliver dicts or JSON strings depending on mode.
        if isinstance(message, str):
            import json

            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                return
        if not isinstance(message, dict):
            return
        token = str(message.get("token") or message.get("instrumentToken") or "")
        symbol = self._token_to_symbol.get(token)
        if not symbol:
            return
        # SmartWebSocketV2 reports prices in paise; divide by 100 to get rupees.
        ltp_paise = message.get("last_traded_price")
        if ltp_paise is None:
            ltp_paise = message.get("ltp")
        if ltp_paise is None:
            return
        ltp = float(ltp_paise) / 100.0 if ltp_paise > 1000 else float(ltp_paise)
        tick = Tick(
            symbol=symbol,
            ltp=ltp,
            volume=message.get("volume_trade_for_the_day"),
        )
        self._publish(tick)
