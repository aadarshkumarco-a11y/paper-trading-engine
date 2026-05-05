"""Portfolio — open positions, trade history, PnL breakdown, analytics."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.charts import equity_curve_chart
from ui.components import render_positions
from ui.state import auto_refresh_if_running, ensure_app
from ui.theme import COLORS
from ui.topbar import render_page_header, render_topbar


def render() -> None:
    app = ensure_app()
    render_page_header("Portfolio", "Positions · trade history · analytics")
    render_topbar(app)

    snap = app.snapshot()
    perf = app.performance()

    metrics = st.columns(5)
    metrics[0].metric("Win rate", f"{perf.win_rate_pct:.1f}%")
    metrics[1].metric("ROI", f"{perf.roi_pct:+.3f}%")
    metrics[2].metric("Profit factor", f"{perf.profit_factor:.2f}" if perf.profit_factor else "—")
    metrics[3].metric("Max drawdown", f"{perf.max_drawdown_pct:.2f}%")
    metrics[4].metric("Trades", f"{perf.trades}")

    st.markdown("&nbsp;")

    st.markdown("##### Equity curve")
    fig = equity_curve_chart(app.equity_df())
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown("##### Open positions")
    render_positions(app)

    st.markdown("##### Trade history")
    df = app.trades_df()
    if df.empty:
        st.info("No trades yet — open the Trading or Strategy page to start.")
    else:
        df_display = df.copy()
        df_display["timestamp"] = pd.to_datetime(df_display["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")

        def _style_side(val: str) -> str:
            color = COLORS["buy"] if val == "BUY" else COLORS["sell"]
            return f"color: {color}; font-weight: 700;"

        styled = df_display.style.format({
            "price": "₹{:,.2f}",
            "brokerage": "₹{:,.2f}",
        }).map(_style_side, subset=["side"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    realized = float(snap.get("realized_pnl", 0.0))
    unrealized = float(snap.get("unrealized_pnl", 0.0))
    total = realized + unrealized
    breakdown = st.columns(3)
    realized_color = COLORS["profit"] if realized >= 0 else COLORS["loss"]
    unreal_color = COLORS["profit"] if unrealized >= 0 else COLORS["loss"]
    total_color = COLORS["profit"] if total >= 0 else COLORS["loss"]
    breakdown[0].markdown(
        f'<div class="glass-card"><div class="title">Realized PnL</div>'
        f'<div style="font-size:1.5rem;font-weight:700;color:{realized_color}">₹{realized:+,.2f}</div></div>',
        unsafe_allow_html=True,
    )
    breakdown[1].markdown(
        f'<div class="glass-card"><div class="title">Unrealized PnL</div>'
        f'<div style="font-size:1.5rem;font-weight:700;color:{unreal_color}">₹{unrealized:+,.2f}</div></div>',
        unsafe_allow_html=True,
    )
    breakdown[2].markdown(
        f'<div class="glass-card"><div class="title">Total PnL</div>'
        f'<div style="font-size:1.5rem;font-weight:700;color:{total_color}">₹{total:+,.2f}</div></div>',
        unsafe_allow_html=True,
    )

    auto_refresh_if_running(app)
