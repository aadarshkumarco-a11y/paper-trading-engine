"""Settings — capital, feed, risk parameters, refresh interval."""
from __future__ import annotations

import streamlit as st

from ui.state import build_app, ensure_app, ss_get
from ui.topbar import render_page_header, render_topbar


def render() -> None:
    app = ensure_app()
    render_page_header("Settings", "Account · feed · risk · auto-refresh")
    render_topbar(app)

    st.caption(
        "These settings only take effect when you create a new engine "
        "(use **Reset engine** below to apply changes)."
    )

    cols = st.columns(3)
    with cols[0]:
        st.markdown("##### Account")
        st.session_state["capital"] = st.number_input(
            "Starting capital (₹)",
            value=float(ss_get("capital", 200_000.0)),
            min_value=1000.0, step=10_000.0,
        )
        st.session_state["feed"] = st.selectbox(
            "Data feed",
            ["yfinance", "kite", "angel", "demo"],
            index=["yfinance", "kite", "angel", "demo"].index(ss_get("feed", "yfinance")),
        )
        st.session_state["respect_hours"] = st.checkbox(
            "Respect NSE market hours (09:15–15:30 IST)",
            value=bool(ss_get("respect_hours", False)),
        )

    with cols[1]:
        st.markdown("##### Risk")
        st.session_state["max_pct"] = st.slider(
            "Max % capital per trade", 0.01, 1.0,
            float(ss_get("max_pct", 0.20)), step=0.01,
        )
        st.session_state["sl"] = st.number_input(
            "Stop-loss %", value=float(ss_get("sl", 0.02)),
            min_value=0.0, step=0.005, format="%.3f",
        )
        st.session_state["tp"] = st.number_input(
            "Take-profit %", value=float(ss_get("tp", 0.04)),
            min_value=0.0, step=0.005, format="%.3f",
        )
        st.session_state["max_loss"] = st.number_input(
            "Max daily loss (₹, 0 = off)",
            value=float(ss_get("max_loss", 0.0)),
            min_value=0.0, step=500.0,
        )

    with cols[2]:
        st.markdown("##### Engine")
        st.session_state["refresh"] = st.slider(
            "Auto-refresh interval (s)", 1, 30, int(ss_get("refresh", 3)),
        )
        if st.button("Reset engine", use_container_width=True, type="secondary"):
            old = ss_get("app")
            if old is not None and old.is_engine_running:
                old.stop()
            st.session_state["app"] = build_app()
            st.toast("Engine reset.", icon="♻️")
            st.rerun()
