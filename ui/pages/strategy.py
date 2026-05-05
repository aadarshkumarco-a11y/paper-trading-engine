"""Strategy — built-in + custom-code editor with sandboxed loader."""
from __future__ import annotations

import streamlit as st

from strategy_engine.code_loader import StrategyCodeError, load_strategy_class
from strategy_engine.registry import registered_strategies
from ui.components import render_status_pill_row, render_trade_log, run_strategy
from ui.state import (
    SAMPLE_STRATEGY_CODE,
    auto_refresh_if_running,
    ensure_app,
    stop_everything,
)
from ui.theme import pill
from ui.topbar import render_page_header, render_topbar


def render() -> None:
    app = ensure_app()
    render_page_header("Strategy", "Built-in & custom Python strategies · sandboxed loader")
    render_topbar(app)

    st.caption(
        "Choose a built-in strategy or paste your own Python code below. Code is "
        "validated (forbidden imports / dunders / file IO) before running."
    )

    cols = st.columns([1.4, 1])

    with cols[0]:
        st.markdown("##### Built-in strategies")
        strategies = sorted(registered_strategies().keys())
        chosen = st.selectbox("Strategy", strategies, key="builtin_strategy_select")
        symbols_text = st.text_input(
            "Symbols",
            value=",".join(app.watchlist() or ["DEMO"]),
            key="strategy_symbols_text",
            help="Comma-separated NSE tickers. Use DEMO to drive the offline feed.",
        )
        qty = int(st.number_input("Quantity per signal", value=10, min_value=1, key="strategy_qty"))

        running = app.is_running
        running_pill = pill(
            "RUNNING" if running else "STOPPED",
            kind="running" if running else "idle",
            show_dot=running,
        )
        st.markdown(running_pill, unsafe_allow_html=True)

        if not running:
            if st.button("▶ Run strategy", type="primary", use_container_width=True, key="run_builtin"):
                run_strategy(app, chosen, symbols_text, qty, code=None)
                st.rerun()
        else:
            if st.button("■ Stop strategy", type="secondary", use_container_width=True, key="stop_builtin"):
                stop_everything()
                st.rerun()

    with cols[1]:
        st.markdown("##### Quick reference")
        st.markdown(
            """
- **RSI** — buys oversold, sells overbought.
- **EMA Crossover** — fast EMA crosses slow EMA.
- **Breakout** — Donchian channel breakout.
            """
        )
        if st.session_state.get("strategy_error"):
            st.error(st.session_state["strategy_error"])
        if st.session_state.get("strategy_info"):
            st.success(st.session_state["strategy_info"])

    st.divider()
    st.markdown("##### Custom strategy editor")
    code = st.text_area(
        "Python source",
        value=st.session_state.get("custom_code", SAMPLE_STRATEGY_CODE),
        height=420,
        key="custom_code",
    )
    btn_validate, btn_run = st.columns([1, 1])
    if btn_validate.button("Validate code", use_container_width=True, key="validate_code_btn"):
        try:
            load_strategy_class(code)
            st.session_state["strategy_info"] = "Code validated — no forbidden imports or syntax errors."
            st.session_state["strategy_error"] = ""
        except StrategyCodeError as exc:
            st.session_state["strategy_info"] = ""
            st.session_state["strategy_error"] = str(exc)
        st.rerun()
    if btn_run.button("▶ Run custom strategy", type="primary", use_container_width=True, key="run_custom"):
        run_strategy(
            app,
            strategy_name="CustomCode",
            symbols_text=st.session_state.get("strategy_symbols_text", "DEMO"),
            quantity=int(st.session_state.get("strategy_qty", 10)),
            code=code,
        )
        st.rerun()

    st.divider()
    st.markdown("##### Strategy logs · last trades")
    render_status_pill_row(app)
    render_trade_log(app)

    auto_refresh_if_running(app)
