import numpy as np
import pandas as pd

from strategy_engine.indicators import atr, ema, rsi, sma


def test_sma_simple():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = sma(s, 3)
    assert np.isnan(out.iloc[0])
    assert out.iloc[2] == 2.0
    assert out.iloc[4] == 4.0


def test_ema_decay():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = ema(s, 3)
    assert out.iloc[-1] > out.iloc[-2]


def test_rsi_constant_series_neutral():
    s = pd.Series([100.0] * 30)
    r = rsi(s, 14)
    # All-flat series → no movement, RSI defined as 50 by our fillna fallback.
    assert r.iloc[-1] == 50.0


def test_rsi_strong_uptrend_high():
    closes = pd.Series(np.linspace(100, 200, 50))
    r = rsi(closes, 14)
    assert r.iloc[-1] > 70


def test_rsi_strong_downtrend_low():
    closes = pd.Series(np.linspace(200, 100, 50))
    r = rsi(closes, 14)
    assert r.iloc[-1] < 30


def test_atr_positive():
    high = pd.Series(np.linspace(105, 200, 50))
    low = pd.Series(np.linspace(95, 190, 50))
    close = pd.Series(np.linspace(100, 195, 50))
    a = atr(high, low, close, 14)
    assert a.dropna().iloc[-1] > 0
