"""Sticky top bar shown on every page (Balance / PnL / Market / Engine)."""
from __future__ import annotations

import streamlit as st

from engine import TradingApp
from ui.theme import COLORS, pill


def render_topbar(app: TradingApp) -> None:
    snap = app.snapshot()
    perf = app.performance()
    market = app.market_status()

    cols = st.columns([1.2, 1.2, 1.2, 1.2, 1.4, 1.6])

    cols[0].metric("Balance", f"₹{snap['cash']:,.2f}")
    cols[1].metric("Equity", f"₹{snap['equity']:,.2f}")

    pnl_value = snap["total_pnl"]
    pnl_label = f"₹{pnl_value:,.2f}"
    pnl_delta = f"{perf.roi_pct:+.3f}%"
    cols[2].metric("Total PnL", pnl_label, delta=pnl_delta)
    cols[3].metric("Realized PnL", f"₹{snap['realized_pnl']:,.2f}")

    market_pill = pill(
        f"NSE {'OPEN' if market['open'] else 'CLOSED'}",
        kind="open" if market["open"] else "closed",
    )
    engine_pill = pill(
        "ENGINE RUNNING" if app.is_engine_running else "ENGINE IDLE",
        kind="running" if app.is_engine_running else "idle",
    )
    strategy_pill = pill(
        "STRATEGY LIVE" if app.is_running else "STRATEGY OFF",
        kind="running" if app.is_running else "idle",
        show_dot=app.is_running,
    )

    cols[4].markdown(
        f'<div class="glass-card"><div class="title">Market</div>'
        f'<div>{market_pill}<div style="color:{COLORS["text_muted"]};font-size:0.78rem;'
        f'margin-top:6px">{market["now_ist"]} IST</div></div></div>',
        unsafe_allow_html=True,
    )
    cols[5].markdown(
        f'<div class="glass-card"><div class="title">Engine</div>'
        f'<div style="display:flex;gap:6px;flex-wrap:wrap">{engine_pill}{strategy_pill}</div></div>',
        unsafe_allow_html=True,
    )

    if snap.get("risk_halted"):
        st.error("⚠ Trading halted by the risk manager (daily loss limit hit).")


def render_page_header(title: str, subtitle: str = "") -> None:
    """Render the small page title strip above the topbar."""
    sub = (
        f'<span style="color:{COLORS["text_muted"]};font-size:0.85rem">{subtitle}</span>'
        if subtitle else ""
    )
    st.markdown(
        f"""
        <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:10px">
          <h1 style="margin:0;font-size:1.45rem;color:{COLORS['text']}">{title}</h1>
          {sub}
        </div>
        """,
        unsafe_allow_html=True,
    )
