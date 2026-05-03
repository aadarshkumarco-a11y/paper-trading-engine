"""Angel One SmartAPI data feed adapter (optional)."""
from __future__ import annotations

import pandas as pd

from data_feed.base import DataFeed
from utils.config import get_settings


class AngelDataFeed(DataFeed):
    def __init__(self) -> None:
        super().__init__()
        try:
            from SmartApi import SmartConnect  # type: ignore
        except ImportError as e:  # pragma: no cover - optional dep
            raise ImportError(
                "smartapi-python is not installed. "
                "`pip install smartapi-python` to use AngelDataFeed."
            ) from e

        settings = get_settings()
        if not (settings.angel_api_key and settings.angel_client_code and settings.angel_password):
            raise RuntimeError(
                "ANGEL_API_KEY, ANGEL_CLIENT_CODE and ANGEL_PASSWORD must be set."
            )

        self._SmartConnect = SmartConnect
        self._client = SmartConnect(api_key=settings.angel_api_key)
        # NOTE: production users should generate the totp from settings.angel_totp_secret
        # and call self._client.generateSession(client_code, password, totp).
        # We intentionally keep this stub minimal so the package imports cleanly
        # without forcing a TOTP roundtrip during test discovery.

    def start(self) -> None:  # pragma: no cover - requires creds
        raise NotImplementedError("AngelDataFeed.start requires SmartAPI WebSocket setup.")

    def stop(self) -> None:  # pragma: no cover - requires creds
        self._running = False

    def get_history(self, symbol: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError
