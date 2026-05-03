"""Pro-grade trading dashboard for the NSE paper trading engine.

Layout (top → bottom, left → right):

    +------------------------------------------------------------+
    |  TOP BAR — Balance · Total PnL · Market status · Engine    |
    +------+------------------------+---------------------------+
    | LEFT |        CENTER          | RIGHT                     |
    | Watch|  Candlestick chart     | Order panel (BUY / SELL)  |
    | list |  + EMA9 / EMA21 / RSI  | (MARKET / LIMIT)          |
    +------+------------------------+---------------------------+
    |  BOTTOM — tabs: Trades · Positions · PnL / Equity curve   |
    +------------------------------------------------------------+

Three top-level tabs:

  * **Terminal** — the layout above (manual trading + live chart)
  * **Strategies** — built-in + custom-code strategy editor with sandboxed loader
  * **Settings** — capital, feed, risk parameters
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import EngineConfig, TradingApp  # noqa: E402
from execution_engine.orders import OrderSide, OrderType  # noqa: E402
from portfolio.risk import RiskConfig  # noqa: E402
from strategy_engine.code_loader import (  # noqa: E402
    CustomCodeStrategy,
    StrategyCodeError,
    load_strategy_class,
)
from strategy_engine.registry import build_strategy, registered_strategies  # noqa: E402
from ui.charts import candlestick_with_indicators, equity_curve_chart  # noqa: E402
from ui.theme import COLORS, inject_theme, pill  # noqa: E402

st.set_page_config(
    page_title="NSE Paper Trading Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_theme()


# ----------------------------------------------------------------------------
# Session helpers
# ----------------------------------------------------------------------------


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


def _ss_get(key: str, default=None):
    return st.session_state.get(key, default)


def _build_app() -> TradingApp:
    """Build (or rebuild) a TradingApp from the values stored in session_state."""
    cfg = EngineConfig(
        initial_capital=float(_ss_get("capital", 200_000.0)),
        feed=_ss_get("feed", "yfinance"),
        respect_market_hours=bool(_ss_get("respect_hours", False)),
        risk=RiskConfig(
            max_capital_pct_per_trade=float(_ss_get("max_pct", 0.20)),
            stop_loss_pct=float(_ss_get("sl", 0.02)) if _ss_get("sl", 0.02) > 0 else None,
            take_profit_pct=float(_ss_get("tp", 0.04)) if _ss_get("tp", 0.04) > 0 else None,
            max_daily_loss=float(_ss_get("max_loss", 0.0)) if _ss_get("max_loss", 0.0) > 0 else None,
        ),
    )
    app = TradingApp(cfg)
    return app


def _ensure_app() -> TradingApp:
    app = _ss_get("app")
    if app is None:
        app = _build_app()
        st.session_state["app"] = app
    return app


def _start_engine_only() -> None:
    app = _ensure_app()
    if not app.is_engine_running:
        app.start_engine_only(symbols=app.watchlist() or _ss_get("default_symbols", ["DEMO"]))


def _stop_everything() -> None:
    app = _ensure_app()
    app.stop()
    st.session_state["strategy_running"] = False


# ----------------------------------------------------------------------------
# Top bar
# ----------------------------------------------------------------------------


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


# ----------------------------------------------------------------------------
# Left panel: watchlist
# ----------------------------------------------------------------------------


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
                _start_engine_only()
            st.session_state["selected_symbol"] = sym
            st.session_state["watchlist_input"] = ""
            st.rerun()
    if add_col2.button("Demo", use_container_width=True, help="Add the offline DEMO symbol"):
        app.add_symbol("DEMO")
        st.session_state["selected_symbol"] = "DEMO"
        if not app.is_engine_running:
            _start_engine_only()
        st.rerun()


# ----------------------------------------------------------------------------
# Center: chart
# ----------------------------------------------------------------------------


def render_chart(app: TradingApp) -> None:
    selected = st.session_state.get("selected_symbol")
    if selected is None:
        watch = app.watchlist()
        if watch:
            selected = watch[0]
            st.session_state["selected_symbol"] = selected
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
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ----------------------------------------------------------------------------
# Right: manual order panel
# ----------------------------------------------------------------------------


def render_order_panel(app: TradingApp) -> None:
    st.markdown("##### Order Panel")
    selected = st.session_state.get("selected_symbol") or (
        app.watchlist()[0] if app.watchlist() else "DEMO"
    )
    sym = st.text_input("Symbol", value=selected, key="order_symbol").strip().upper()
    qty = int(st.number_input("Quantity", value=int(_ss_get("order_qty", 1)), min_value=1, step=1, key="order_qty"))
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
        except Exception as exc:  # noqa: BLE001 - surface to user
            st.error(f"Order rejected: {exc}")
    if btn_sell.button("SELL", type="secondary", use_container_width=True, key="manual_sell"):
        try:
            app.place_manual_order(sym, OrderSide.SELL, qty, order_type=order_type, limit_price=limit_price)
            st.toast(f"SELL {qty} {sym} submitted", icon="🔴")
        except Exception as exc:  # noqa: BLE001 - surface to user
            st.error(f"Order rejected: {exc}")

    if not app.is_engine_running:
        if st.button("Start engine (live prices)", type="primary", use_container_width=True, key="start_engine_btn"):
            if sym:
                app.add_symbol(sym)
            _start_engine_only()
            st.rerun()
    else:
        if st.button("Stop engine", type="secondary", use_container_width=True, key="stop_engine_btn"):
            _stop_everything()
            st.rerun()


# ----------------------------------------------------------------------------
# Bottom: trades / positions / equity tabs
# ----------------------------------------------------------------------------


def render_bottom_panel(app: TradingApp) -> None:
    tab_trades, tab_positions, tab_pnl = st.tabs(["Trade log", "Open positions", "Equity & PnL"])

    with tab_trades:
        df = app.trades_df()
        if df.empty:
            st.info("No trades yet — place a manual order or start a strategy.")
        else:
            df_display = df.copy()
            df_display["timestamp"] = pd.to_datetime(df_display["timestamp"]).dt.strftime("%H:%M:%S")
            df_display["price"] = df_display["price"].map(lambda v: f"₹{v:,.2f}")
            df_display["brokerage"] = df_display["brokerage"].map(lambda v: f"₹{v:,.2f}")
            st.dataframe(df_display, use_container_width=True, hide_index=True)

    with tab_positions:
        snap = app.snapshot()
        positions = snap.get("open_positions") or []
        if not positions:
            st.info("No open positions.")
        else:
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

    with tab_pnl:
        equity_df = app.equity_df()
        perf = app.performance()
        m = st.columns(4)
        m[0].metric("Win rate", f"{perf.win_rate * 100:.1f}%")
        m[1].metric("ROI", f"{perf.roi_pct:+.3f}%")
        m[2].metric("Profit factor", f"{perf.profit_factor:.2f}" if perf.profit_factor else "—")
        m[3].metric("Max drawdown", f"{perf.max_drawdown_pct:.2f}%")
        fig = equity_curve_chart(equity_df)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ----------------------------------------------------------------------------
# Strategies tab
# ----------------------------------------------------------------------------


def render_strategies_tab(app: TradingApp) -> None:
    st.markdown("### Strategy engine")
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
                _run_strategy(app, chosen, symbols_text, qty, code=None)
                st.rerun()
        else:
            if st.button("■ Stop strategy", type="secondary", use_container_width=True, key="stop_builtin"):
                _stop_everything()
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
        _run_strategy(
            app,
            strategy_name="CustomCode",
            symbols_text=st.session_state.get("strategy_symbols_text", "DEMO"),
            quantity=int(st.session_state.get("strategy_qty", 10)),
            code=code,
        )
        st.rerun()


def _run_strategy(
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
    except Exception as exc:  # noqa: BLE001 - surface as UI error
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


# ----------------------------------------------------------------------------
# Settings tab
# ----------------------------------------------------------------------------


def render_settings_tab() -> None:
    st.markdown("### Settings")
    st.caption(
        "These settings only take effect when you create a new engine "
        "(use **Reset engine** below to apply changes)."
    )
    cols = st.columns(3)
    with cols[0]:
        st.markdown("##### Account")
        st.session_state["capital"] = st.number_input(
            "Starting capital (₹)",
            value=float(_ss_get("capital", 200_000.0)),
            min_value=1000.0, step=10_000.0,
        )
        st.session_state["feed"] = st.selectbox(
            "Data feed",
            ["yfinance", "kite", "angel", "demo"],
            index=["yfinance", "kite", "angel", "demo"].index(_ss_get("feed", "yfinance")),
        )
        st.session_state["respect_hours"] = st.checkbox(
            "Respect NSE market hours (09:15–15:30 IST)",
            value=bool(_ss_get("respect_hours", False)),
        )

    with cols[1]:
        st.markdown("##### Risk")
        st.session_state["max_pct"] = st.slider(
            "Max % capital per trade", 0.01, 1.0,
            float(_ss_get("max_pct", 0.20)), step=0.01,
        )
        st.session_state["sl"] = st.number_input(
            "Stop-loss %", value=float(_ss_get("sl", 0.02)),
            min_value=0.0, step=0.005, format="%.3f",
        )
        st.session_state["tp"] = st.number_input(
            "Take-profit %", value=float(_ss_get("tp", 0.04)),
            min_value=0.0, step=0.005, format="%.3f",
        )
        st.session_state["max_loss"] = st.number_input(
            "Max daily loss (₹, 0 = off)",
            value=float(_ss_get("max_loss", 0.0)),
            min_value=0.0, step=500.0,
        )

    with cols[2]:
        st.markdown("##### Engine")
        st.session_state["refresh"] = st.slider(
            "Auto-refresh interval (s)", 1, 30, int(_ss_get("refresh", 3)),
        )
        if st.button("Reset engine", use_container_width=True, type="secondary"):
            old = _ss_get("app")
            if old is not None and old.is_engine_running:
                old.stop()
            st.session_state["app"] = _build_app()
            st.toast("Engine reset.", icon="♻️")
            st.rerun()


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main() -> None:
    app = _ensure_app()

    st.markdown(
        f"""
        <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:10px">
          <h1 style="margin:0;font-size:1.55rem;color:{COLORS['text']}">📈 NSE Paper Trading Terminal</h1>
          <span style="color:{COLORS['text_muted']};font-size:0.85rem">
            paper trading · zero real capital at risk
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_topbar(app)

    tab_terminal, tab_strategies, tab_settings = st.tabs(["Terminal", "Strategies", "Settings"])

    with tab_terminal:
        left, center, right = st.columns([1.0, 2.6, 1.1])
        with left:
            render_watchlist(app)
        with center:
            render_chart(app)
        with right:
            render_order_panel(app)
        st.markdown("&nbsp;")
        render_bottom_panel(app)

    with tab_strategies:
        render_strategies_tab(app)

    with tab_settings:
        render_settings_tab()

    refresh = int(_ss_get("refresh", 3))
    if app.is_engine_running:
        time.sleep(refresh)
        st.rerun()


if __name__ == "__main__":
    main()
