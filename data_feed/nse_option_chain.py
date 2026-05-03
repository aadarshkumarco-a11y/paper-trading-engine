"""NSE public option-chain fetcher.

Uses the unauthenticated nseindia.com endpoints. NSE rate-limits aggressively
and requires a session cookie + browser-like headers, so we keep a single
`requests.Session` and refresh cookies on demand. All network errors are
caught and surfaced as empty results so the engine never crashes.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from utils.logger import get_logger

NSE_HOME = "https://www.nseindia.com"
OPTION_CHAIN_INDEX = "https://www.nseindia.com/api/option-chain-indices"
OPTION_CHAIN_EQUITY = "https://www.nseindia.com/api/option-chain-equities"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/option-chain",
    "Connection": "keep-alive",
}


@dataclass
class OptionContract:
    symbol: str
    strike: float
    expiry: str
    option_type: str  # "CE" or "PE"
    ltp: float
    bid: float
    ask: float
    iv: float | None
    oi: int
    volume: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class NSEOptionChain:
    INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}

    def __init__(self, timeout: float = 5.0) -> None:
        self.logger = get_logger("NSEOptionChain")
        self.timeout = timeout
        self._lock = threading.RLock()
        self._session: requests.Session | None = None

    def _ensure_session(self) -> requests.Session:
        with self._lock:
            if self._session is None:
                s = requests.Session()
                s.headers.update(DEFAULT_HEADERS)
                try:
                    s.get(NSE_HOME, timeout=self.timeout)
                except requests.RequestException:
                    self.logger.warning("Could not warm NSE session cookies")
                self._session = s
            return self._session

    def _fetch(self, symbol: str) -> dict[str, Any]:
        symbol = symbol.upper()
        url = OPTION_CHAIN_INDEX if symbol in self.INDEX_SYMBOLS else OPTION_CHAIN_EQUITY
        s = self._ensure_session()
        try:
            r = s.get(url, params={"symbol": symbol}, timeout=self.timeout)
            if r.status_code == 401:
                self._session = None
                s = self._ensure_session()
                r = s.get(url, params={"symbol": symbol}, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            self.logger.exception("NSE option-chain fetch failed for %s", symbol)
            return {}

    def get_chain(self, symbol: str, expiry: str | None = None) -> list[OptionContract]:
        data = self._fetch(symbol)
        records = data.get("records", {}) if isinstance(data, dict) else {}
        rows = records.get("data", []) or []
        out: list[OptionContract] = []
        for row in rows:
            row_expiry = row.get("expiryDate")
            if expiry and row_expiry != expiry:
                continue
            for opt_type in ("CE", "PE"):
                leg = row.get(opt_type)
                if not leg:
                    continue
                out.append(
                    OptionContract(
                        symbol=symbol,
                        strike=float(row.get("strikePrice", 0) or 0),
                        expiry=row_expiry or "",
                        option_type=opt_type,
                        ltp=float(leg.get("lastPrice") or 0.0),
                        bid=float(leg.get("bidprice") or 0.0),
                        ask=float(leg.get("askPrice") or 0.0),
                        iv=float(leg.get("impliedVolatility") or 0.0) or None,
                        oi=int(leg.get("openInterest") or 0),
                        volume=int(leg.get("totalTradedVolume") or 0),
                    )
                )
        return out

    def get_underlying_price(self, symbol: str) -> float | None:
        data = self._fetch(symbol)
        if not data:
            return None
        underlying = data.get("records", {}).get("underlyingValue")
        return float(underlying) if underlying is not None else None

    def get_atm_strike(self, symbol: str, step: float | None = None) -> float | None:
        spot = self.get_underlying_price(symbol)
        if spot is None:
            return None
        step = step or self._strike_step(symbol)
        return round(spot / step) * step

    @staticmethod
    def _strike_step(symbol: str) -> float:
        return {
            "NIFTY": 50.0,
            "FINNIFTY": 50.0,
            "MIDCPNIFTY": 25.0,
            "BANKNIFTY": 100.0,
        }.get(symbol.upper(), 50.0)

    def get_expiries(self, symbol: str) -> list[str]:
        data = self._fetch(symbol)
        return list(data.get("records", {}).get("expiryDates", []) or [])

    @staticmethod
    def parse_expiry(expiry: str) -> datetime | None:
        for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(expiry, fmt)
            except ValueError:
                continue
        return None
