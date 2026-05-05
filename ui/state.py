"""Shared state helpers and TradingApp lifecycle for the multi-page UI.

These helpers live in one module so every page can access the same engine,
session-state defaults, and start/stop helpers.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from engine import EngineConfig, TradingApp
from portfolio.risk import RiskConfig

SAMPLE_STRATEGY_CODE = '''\
"""Custom strategy template — edit this to your liking.

Two supported shapes:
  1. Subclass `Strategy` (recommended, full access to rolling buffers).
  2. Plain class with `on_tick(self, data)` returning "BUY" / "SELL" / "HOLD".

The dict-based `on_tick(data)` receives:
  data["price"], data["ema_short"], data["ema_long"], data["history"], ...
"""

class Strategy:
    def __init__(self):
        self.position = 0  # +1 long, 0 flat

    def on_tick(self, data):
        price = data["price"]
        ema_short = data["ema_short"]
        ema_long = data["ema_long"]

        if self.position == 0 and ema_short > ema_long * 1.001:
            self.position = 1
            return "BUY"
        if self.position == 1 and ema_short < ema_long * 0.999:
            self.position = 0
            return "SELL"
        return "HOLD"
'''


def ss_get(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def build_app() -> TradingApp:
    """Build a fresh TradingApp from the values stored in session_state."""
    cfg = EngineConfig(
        initial_capital=float(ss_get("capital", 200_000.0)),
        feed=ss_get("feed", "yfinance"),
        respect_market_hours=bool(ss_get("respect_hours", False)),
        risk=RiskConfig(
            max_capital_pct_per_trade=float(ss_get("max_pct", 0.20)),
            stop_loss_pct=float(ss_get("sl", 0.02)) if ss_get("sl", 0.02) > 0 else None,
            take_profit_pct=float(ss_get("tp", 0.04)) if ss_get("tp", 0.04) > 0 else None,
            max_daily_loss=float(ss_get("max_loss", 0.0)) if ss_get("max_loss", 0.0) > 0 else None,
        ),
    )
    return TradingApp(cfg)


def ensure_app() -> TradingApp:
    """Return the cached TradingApp, creating one if needed."""
    app = ss_get("app")
    if app is None:
        app = build_app()
        st.session_state["app"] = app
    return app


def start_engine_only() -> None:
    """Start the data feed/execution layer without a strategy.

    Used so manual orders can be placed even before any strategy is running.
    """
    app = ensure_app()
    if not app.is_engine_running:
        app.start_engine_only(symbols=app.watchlist() or ss_get("default_symbols", ["DEMO"]))


def stop_everything() -> None:
    app = ensure_app()
    app.stop()
    st.session_state["strategy_running"] = False


def auto_refresh_if_running(app: TradingApp) -> None:
    """Sleep + rerun loop used at the bottom of every page when the engine is live."""
    import time

    refresh = int(ss_get("refresh", 3))
    if app.is_engine_running:
        time.sleep(refresh)
        st.rerun()
