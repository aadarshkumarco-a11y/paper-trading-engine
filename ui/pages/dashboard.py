"""Dashboard — high-level account overview."""
from __future__ import annotations

import streamlit as st

from ui.charts import equity_curve_chart
from ui.components import render_chart, render_positions, render_trade_log
from ui.state import auto_refresh_if_running, ensure_app
from ui.theme import COLORS, pill
from ui.topbar import render_page_header, render_topbar


def render() -> None:
    app = ensure_app()
    render_page_header("Dashboard", "Account overview · paper trading · zero real capital at risk")
    render_topbar(app)

    snap = app.snapshot()
    perf = app.performance()
    market = app.market_status()

    quick = st.columns(4)
    quick[0].markdown(
        f'<div class="glass-card"><div class="title">Open positions</div>'
        f'<div style="font-size:1.6rem;font-weight:700">{len(snap.get("open_positions") or [])}</div>'
        f'<div style="color:{COLORS["text_muted"]};font-size:0.78rem">live</div></div>',
        unsafe_allow_html=True,
    )
    quick[1].markdown(
        f'<div class="glass-card"><div class="title">Total trades</div>'
        f'<div style="font-size:1.6rem;font-weight:700">{perf.trades}</div>'
        f'<div style="color:{COLORS["text_muted"]};font-size:0.78rem">since session start</div></div>',
        unsafe_allow_html=True,
    )
    win_color = COLORS["profit"] if perf.win_rate_pct >= 50 else COLORS["text_muted"]
    quick[2].markdown(
        f'<div class="glass-card"><div class="title">Win rate</div>'
        f'<div style="font-size:1.6rem;font-weight:700;color:{win_color}">{perf.win_rate_pct:.1f}%</div>'
        f'<div style="color:{COLORS["text_muted"]};font-size:0.78rem">round-trips</div></div>',
        unsafe_allow_html=True,
    )
    dd_color = COLORS["loss"] if perf.max_drawdown_pct < -1 else COLORS["text_muted"]
    quick[3].markdown(
        f'<div class="glass-card"><div class="title">Max drawdown</div>'
        f'<div style="font-size:1.6rem;font-weight:700;color:{dd_color}">{perf.max_drawdown_pct:.2f}%</div>'
        f'<div style="color:{COLORS["text_muted"]};font-size:0.78rem">peak-to-trough</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("&nbsp;")

    left, right = st.columns([1.6, 1])
    with left:
        st.markdown("##### Equity curve")
        fig = equity_curve_chart(app.equity_df())
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with right:
        st.markdown("##### Market status")
        market_pill_html = pill(
            f"NSE {'OPEN' if market['open'] else 'CLOSED'}",
            kind="open" if market["open"] else "closed",
        )
        st.markdown(
            f'<div class="glass-card" style="padding:18px">{market_pill_html}'
            f'<div style="margin-top:10px;color:{COLORS["text_muted"]};font-size:0.85rem">'
            f'{market["now_ist"]} IST</div></div>',
            unsafe_allow_html=True,
        )

        watch = app.watchlist()
        if watch:
            st.markdown("##### Top symbol")
            render_chart(app, compact=True)
        else:
            st.info("No symbols in watchlist yet. Open the Trading page to add one.")

    st.markdown("&nbsp;")

    bottom_left, bottom_right = st.columns(2)
    with bottom_left:
        st.markdown("##### Recent trades")
        render_trade_log(app)
    with bottom_right:
        st.markdown("##### Open positions")
        render_positions(app)

    auto_refresh_if_running(app)
