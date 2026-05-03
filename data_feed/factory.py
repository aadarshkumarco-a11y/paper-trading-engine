"""Factory for creating data feeds based on configuration."""
from __future__ import annotations

from data_feed.base import DataFeed
from utils.config import get_settings
from utils.logger import get_logger


def create_feed(kind: str | None = None) -> DataFeed:
    settings = get_settings()
    logger = get_logger("data_feed.factory")
    selected = (kind or settings.data_feed or "yfinance").lower()
    logger.info("Creating data feed: %s", selected)
    if selected == "yfinance":
        from data_feed.yfinance_feed import YFinanceDataFeed

        return YFinanceDataFeed()
    if selected == "kite":
        from data_feed.kite_feed import KiteDataFeed

        return KiteDataFeed()
    if selected == "angel":
        from data_feed.angel_feed import AngelDataFeed

        return AngelDataFeed()
    raise ValueError(
        f"Unknown data feed '{selected}'. Supported: yfinance, kite, angel."
    )
