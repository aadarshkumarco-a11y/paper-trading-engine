"""Reusable Streamlit render components shared across pages.

Originally lived inline in ``ui/streamlit_app.py``; split out here so each
page (Dashboard / Trading / Strategy / Portfolio / Settings) can import and
compose them without circular imports.
"""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from engine import TradingApp
from execution_engine.orders import OrderSide, OrderType
from strategy_engine.code_loader import (
    CustomCodeStrategy,
    StrategyCodeError,
    load_strategy_class,
)
from strategy_engine.registry import build_strategy
from ui.charts import candlestick_with_indicators, equity_curve_chart
from ui.state import ss_get, start_engine_only, stop_everything
from ui.theme import COLORS, pill

# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------


def render_watchlist(app: TradingApp) -> None:
    st.markdown("##### Watchlist")
    prices = app.last_prices()
    last_seen: dict[str, float] = st.session_state.setdefault("watchlist_last", {})

    for sym in app.watchlist():
        price = prices.get(sym)
        prev = last_seen.get(sym)
        direction = ""
        if price is not None and prev is not None:
            if price > prev:
                direction = "up"
            elif price < prev:
                direction = "down"
        if price is not None:
            last_seen[sym] = price

        price_str = f"₹{price:,.2f}" if price is not None else "—"

        row_cols = st.columns([4, 1])
        row_cols[0].markdown(
            f'<div class="watchlist-row">'
            f'<span class="sym">{sym}</span>'
            f'<span class="price {direction}">{price_str}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        if row_cols[1].button("✕", key=f"rm_{sym}", help=f"Remove {sym} from watchlist"):
            app.remove_symbol(sym)
            st.session_state["selected_symbol"] = (
                next(iter(app.watchlist()), None)
                if st.session_state.get("selected_symbol") == sym
                else st.session_state.get("selected_symbol")
            )
            st.rerun()
        if row_cols[0].button(
            "Select",
            key=f"sel_{sym}",
            help="Show this symbol in the chart and order panel",
            use_container_width=True,
        ):
            st.session_state["selected_symbol"] = sym
            st.rerun()

    add = st.text_input("Add symbol", key="watchlist_input", placeholder="e.g. INFY")
    add_col1, add_col2 = st.columns([1, 1])
    if add_col1.button("Add", use_container_width=True):
        sym = add.strip().upper()
        if sym:
            app.add_symbol(sym)
            if not app.is_engine_running:
                start_engine_only()
            st.session_state["selected_symbol"] = sym
            st.session_state["watchlist_input"] = ""
            st.rerun()
    if add_col2.button("Demo", use_container_width=True, help="Add the offline DEMO symbol"):
        app.add_symbol("DEMO")
        st.session_state["selected_symbol"] = "DEMO"
        if not app.is_engine_running:
            start_engine_only()
        st.rerun()


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------


def render_chart(app: TradingApp, *, compact: bool = False) -> None:
    selected = st.session_state.get("selected_symbol")
    if selected is None:
        watch = app.watchlist()
        if watch:
            selected = watch[0]
            st.session_state["selected_symbol"] = selected

    if compact:
        st.markdown(f"##### {selected or '(no symbol)'}")
        freq, fast, slow = "15s", 9, 21
    else:
        cols = st.columns([2, 1, 1, 1])
        cols[0].markdown(f"##### Chart — {selected or '(no symbol)'}")
        freq = cols[1].selectbox("Bar size", ["5s", "15s", "30s", "1min", "5min"], index=1, key="chart_freq")
        fast = int(cols[2].number_input("EMA fast", value=9, min_value=2, max_value=200, step=1))
        slow = int(cols[3].number_input("EMA slow", value=21, min_value=3, max_value=400, step=1))

    if selected is None:
        st.info("Add a symbol from the watchlist to see live prices.")
        return

    ohlc = app.ohlc(selected, freq=freq, lookback=200)
    fig = candlestick_with_indicators(
        ohlc,
        symbol=selected,
        show_ema_fast=fast,
        show_ema_slow=slow,
        height=320 if compact else 460,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ---------------------------------------------------------------------------
# Order panel
# ---------------------------------------------------------------------------


def render_order_panel(app: TradingApp) -> None:
    st.markdown("##### Order Panel")
    selected = st.session_state.get("selected_symbol") or (
        app.watchlist()[0] if app.watchlist() else "DEMO"
    )
    sym = st.text_input("Symbol", value=selected, key="order_symbol").strip().upper()
    qty = int(st.number_input("Quantity", value=int(ss_get("order_qty", 1)), min_value=1, step=1, key="order_qty"))
    order_type_label = st.selectbox("Order type", ["MARKET", "LIMIT"], key="order_type_sel")
    order_type = OrderType(order_type_label)
    limit_price: float | None = None
    if order_type is OrderType.LIMIT:
        last = app.feed.get_last_price(sym) or 100.0
        limit_price = float(
            st.number_input("Limit price (₹)", value=float(last), min_value=0.01, step=0.05, format="%.2f")
        )

    last_price = app.feed.get_last_price(sym)
    if last_price is not None:
        st.caption(f"Last traded price: ₹{last_price:,.2f}")
    elif app.is_engine_running:
        st.caption("Waiting for first tick…")
    else:
        st.caption("Engine idle — start engine to see live prices.")

    btn_buy, btn_sell = st.columns(2)
    if btn_buy.button("BUY", type="primary", use_container_width=True, key="manual_buy"):
        try:
            app.place_manual_order(sym, OrderSide.BUY, qty, order_type=order_type, limit_price=limit_price)
            st.toast(f"BUY {qty} {sym} submitted", icon="🟢")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Order rejected: {exc}")
    if btn_sell.button("SELL", type="secondary", use_container_width=True, key="manual_sell"):
        try:
            app.place_manual_order(sym, OrderSide.SELL, qty, order_type=order_type, limit_price=limit_price)
            st.toast(f"SELL {qty} {sym} submitted", icon="🔴")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Order rejected: {exc}")

    if not app.is_engine_running:
        if st.button("Start engine (live prices)", type="primary", use_container_width=True, key="start_engine_btn"):
            if sym:
                app.add_symbol(sym)
            start_engine_only()
            st.rerun()
    else:
        if st.button("Stop engine", type="secondary", use_container_width=True, key="stop_engine_btn"):
            stop_everything()
            st.rerun()


# ---------------------------------------------------------------------------
# Trade log / Positions / Equity tables
# ---------------------------------------------------------------------------


def render_trade_log(app: TradingApp) -> None:
    df = app.trades_df()
    if df.empty:
        st.info("No trades yet — place a manual order or start a strategy.")
        return
    df_display = df.copy()
    df_display["timestamp"] = pd.to_datetime(df_display["timestamp"]).dt.strftime("%H:%M:%S")
    df_display["price"] = df_display["price"].map(lambda v: f"₹{v:,.2f}")
    df_display["brokerage"] = df_display["brokerage"].map(lambda v: f"₹{v:,.2f}")
    st.dataframe(df_display, use_container_width=True, hide_index=True)


def render_positions(app: TradingApp) -> None:
    snap = app.snapshot()
    positions = snap.get("open_positions") or []
    if not positions:
        st.info("No open positions.")
        return
    df = pd.DataFrame(positions)

    def _style_pnl(val):
        color = COLORS["profit"] if val >= 0 else COLORS["loss"]
        return f"color: {color}; font-weight: 600;"

    styled = df.style.format({
        "avg_price": "₹{:,.2f}",
        "last_price": "₹{:,.2f}",
        "market_value": "₹{:,.2f}",
        "unrealized_pnl": "₹{:+,.2f}",
        "realized_pnl": "₹{:+,.2f}",
    }).map(_style_pnl, subset=["unrealized_pnl", "realized_pnl"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


def render_equity_panel(app: TradingApp) -> None:
    equity_df = app.equity_df()
    perf = app.performance()
    m = st.columns(4)
    m[0].metric("Win rate", f"{perf.win_rate_pct:.1f}%")
    m[1].metric("ROI", f"{perf.roi_pct:+.3f}%")
    m[2].metric("Profit factor", f"{perf.profit_factor:.2f}" if perf.profit_factor else "—")
    m[3].metric("Max drawdown", f"{perf.max_drawdown_pct:.2f}%")
    fig = equity_curve_chart(equity_df)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ---------------------------------------------------------------------------
# Strategy runner (used by Strategy page)
# ---------------------------------------------------------------------------


def run_strategy(
    app: TradingApp,
    strategy_name: str,
    symbols_text: str,
    quantity: int,
    code: str | None,
) -> None:
    symbols = [s.strip().upper() for s in symbols_text.split(",") if s.strip()]
    if not symbols:
        st.session_state["strategy_error"] = "At least one symbol is required."
        return
    try:
        if code is not None:
            loaded = load_strategy_class(code)
            strategy = CustomCodeStrategy(loaded, symbols=symbols, quantity=quantity)
        else:
            strategy = build_strategy(strategy_name, symbols=symbols, quantity=quantity)
    except StrategyCodeError as exc:
        st.session_state["strategy_error"] = str(exc)
        return
    except Exception as exc:  # noqa: BLE001
        st.session_state["strategy_error"] = f"Failed to build strategy: {exc}"
        return

    if app.is_running:
        app.stop()
        time.sleep(0.2)

    for s in symbols:
        app.add_symbol(s)
    app.set_strategy(strategy)
    app.start()
    st.session_state["strategy_error"] = ""
    st.session_state["strategy_info"] = f"{type(strategy).__name__} running on {symbols}."


def render_status_pill_row(app: TradingApp) -> None:
    """Compact engine + strategy pill row used on Strategy / Trading pages."""
    engine_pill = pill(
        "ENGINE RUNNING" if app.is_engine_running else "ENGINE IDLE",
        kind="running" if app.is_engine_running else "idle",
    )
    strategy_pill = pill(
        "STRATEGY LIVE" if app.is_running else "STRATEGY OFF",
        kind="running" if app.is_running else "idle",
        show_dot=app.is_running,
    )
    st.markdown(
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">'
        f"{engine_pill}{strategy_pill}</div>",
        unsafe_allow_html=True,
    )
