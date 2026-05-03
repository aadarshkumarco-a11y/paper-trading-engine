"""Lazy loader for Angel One's scrip master JSON.

Angel publishes the entire NSE/BSE/MCX/NFO instrument list at
``https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json``.

We download it once per process, cache it on disk for 24 hours, and expose
fast `lookup(symbol, exchange)` → token resolution. Required by
SmartWebSocketV2 (which subscribes by numeric token, not by ticker).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import requests

from utils.config import PROJECT_ROOT
from utils.logger import get_logger

ANGEL_SCRIP_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)
EXCHANGE_TYPE = {
    "NSE": 1,
    "NSE_CM": 1,
    "NFO": 2,
    "BSE": 3,
    "BFO": 4,
    "MCX": 5,
    "NCX": 7,
    "CDS": 13,
}


class AngelSymbolMaster:
    """Thread-safe scrip-master cache."""

    def __init__(self, cache_path: Path | None = None, ttl_seconds: int = 24 * 3600) -> None:
        self.cache_path = Path(cache_path or PROJECT_ROOT / "runtime" / "angel_scrip_master.json")
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = int(ttl_seconds)
        self._lock = threading.RLock()
        self._records: list[dict] | None = None
        self.logger = get_logger("AngelSymbolMaster")

    def load(self, force_refresh: bool = False) -> list[dict]:
        with self._lock:
            if self._records is not None and not force_refresh:
                return self._records
            if (
                not force_refresh
                and self.cache_path.exists()
                and time.time() - self.cache_path.stat().st_mtime < self.ttl_seconds
            ):
                try:
                    with self.cache_path.open() as fh:
                        self._records = json.load(fh)
                    return self._records
                except (OSError, json.JSONDecodeError):
                    self.logger.warning("Corrupt cache; re-downloading")

            self.logger.info("Downloading Angel scrip master (~3 MB)...")
            r = requests.get(ANGEL_SCRIP_URL, timeout=30)
            r.raise_for_status()
            data = r.json()
            with self.cache_path.open("w") as fh:
                json.dump(data, fh)
            self._records = data
            return data

    def lookup(self, symbol: str, exchange: str = "NSE") -> dict | None:
        """Resolve an NSE/NFO trading symbol to its instrument record.

        For NSE equities, Angel's symbol is suffixed with ``-EQ`` (e.g. ``SBIN-EQ``).
        We accept both ``SBIN`` and ``SBIN-EQ``.
        """
        symbol = symbol.strip().upper()
        exchange = exchange.upper()
        records = self.load()
        candidates = [
            r for r in records
            if r.get("exch_seg", "").upper() == exchange
            and r.get("symbol", "").upper() in {symbol, f"{symbol}-EQ"}
        ]
        if candidates:
            return candidates[0]
        # Fallback: name match (useful for indexes like NIFTY)
        candidates = [r for r in records if r.get("name", "").upper() == symbol]
        return candidates[0] if candidates else None

    def token_for(self, symbol: str, exchange: str = "NSE") -> str | None:
        rec = self.lookup(symbol, exchange)
        return rec.get("token") if rec else None

    @staticmethod
    def exchange_type(exchange: str) -> int:
        return EXCHANGE_TYPE.get(exchange.upper(), 1)
