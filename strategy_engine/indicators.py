"""Vectorized technical indicators."""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-smoothed RSI.

    Edge cases:
    - Constant or warm-up period → returns 50 (neutral) for unstable values.
    - All-gain window → 100. All-loss window → 0.
    """
    if len(series) < period + 1:
        return pd.Series([np.nan] * len(series), index=series.index)
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    out = pd.Series(np.nan, index=series.index, dtype=float)
    nonzero_loss = avg_loss > 0
    rs = avg_gain[nonzero_loss] / avg_loss[nonzero_loss]
    out.loc[nonzero_loss] = 100 - (100 / (1 + rs))
    # Pure uptrend (no losses): RSI = 100 if there was at least one gain, else 50
    pure_up = (avg_loss == 0) & (avg_gain > 0)
    out.loc[pure_up] = 100.0
    flat = (avg_loss == 0) & (avg_gain == 0)
    out.loc[flat] = 50.0
    return out.fillna(50.0)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
