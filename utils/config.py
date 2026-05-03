"""Application configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is optional
    pass


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    """Runtime configuration for the engine."""

    db_path: str = field(
        default_factory=lambda: _env("PAPER_TRADING_DB", "runtime/paper_trading.db")
    )
    log_level: str = field(
        default_factory=lambda: _env("PAPER_TRADING_LOG_LEVEL", "INFO")
    )
    data_feed: str = field(
        default_factory=lambda: _env("PAPER_TRADING_DATA_FEED", "yfinance")
    )
    kite_api_key: str = field(default_factory=lambda: _env("KITE_API_KEY"))
    kite_api_secret: str = field(default_factory=lambda: _env("KITE_API_SECRET"))
    kite_access_token: str = field(default_factory=lambda: _env("KITE_ACCESS_TOKEN"))
    angel_api_key: str = field(default_factory=lambda: _env("ANGEL_API_KEY"))
    angel_client_code: str = field(default_factory=lambda: _env("ANGEL_CLIENT_CODE"))
    angel_password: str = field(default_factory=lambda: _env("ANGEL_PASSWORD"))
    angel_totp_secret: str = field(default_factory=lambda: _env("ANGEL_TOTP_SECRET"))

    @property
    def db_absolute_path(self) -> Path:
        path = Path(self.db_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
