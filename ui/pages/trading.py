"""Trading — full live terminal (watchlist | chart | order panel + bottom tabs)."""
from __future__ import annotations

import streamlit as st

from ui.components import (
    render_chart,
    render_equity_panel,
    render_order_panel,
    render_positions,
    render_trade_log,
    render_watchlist,
)
from ui.state import auto_refresh_if_running, ensure_app
from ui.topbar import render_page_header, render_topbar


def render() -> None:
    app = ensure_app()
    render_page_header("Trading Terminal", "Live chart · manual orders · watchlist")
    render_topbar(app)

    left, center, right = st.columns([1.0, 2.6, 1.1])
    with left:
        render_watchlist(app)
    with center:
        render_chart(app)
    with right:
        render_order_panel(app)

    st.markdown("&nbsp;")

    tab_trades, tab_positions, tab_pnl = st.tabs(["Trade log", "Open positions", "Equity & PnL"])
    with tab_trades:
        render_trade_log(app)
    with tab_positions:
        render_positions(app)
    with tab_pnl:
        render_equity_panel(app)

    auto_refresh_if_running(app)
