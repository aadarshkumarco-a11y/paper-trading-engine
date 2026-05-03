"""Lightweight logger factory."""
from __future__ import annotations

import logging
import sys
from functools import lru_cache

from utils.config import get_settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


@lru_cache(maxsize=64)
def get_logger(name: str = "paper_trading") -> logging.Logger:
    settings = get_settings()
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(settings.log_level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
