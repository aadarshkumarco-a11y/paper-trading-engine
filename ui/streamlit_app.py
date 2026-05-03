"""Streamlit dashboard for the paper trading engine."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import EngineConfig, TradingApp  # noqa: E402
from portfolio.risk import RiskConfig  # noqa: E402
from strategy_engine.registry import build_strategy, registered_strategies  # noqa: E402

st.set_page_config(
    page_title="NSE Paper Trading",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)


def _ensure_app() -> TradingApp | None:
    return st.session_state.get("app")


def _start_app(
    strategy_name: str,
    symbols: list[str],
    capital: float,
    quantity: int,
    feed: str,
    max_pct: float,
    sl: float,
    tp: float,
    max_loss: float,
    respect_hours: bool,
) -> None:
    risk = RiskConfig(
        max_capital_pct_per_trade=max_pct,
        stop_loss_pct=sl if sl > 0 else None,
        take_profit_pct=tp if tp > 0 else None,
        max_daily_loss=max_loss if max_loss > 0 else None,
    )
    app = TradingApp(EngineConfig(
        initial_capital=capital,
        feed=feed,
        respect_market_hours=respect_hours,
        risk=risk,
    ))
    strategy = build_strategy(strategy_name, symbols=symbols, quantity=quantity)
    app.set_strategy(strategy)
    app.start()
    st.session_state["app"] = app
    st.session_state["strategy_name"] = strategy_name
    st.session_state["symbols"] = symbols


def _stop_app() -> None:
    app = _ensure_app()
    if app is not None:
        app.stop()


def render_sidebar() -> None:
    st.sidebar.header("Configuration")
    strategies = sorted(registered_strategies().keys())
    strategy = st.sidebar.selectbox("Strategy", strategies, index=0)
    feed = st.sidebar.selectbox("Data feed", ["yfinance", "kite", "angel", "demo"], index=0)
    symbols_text = st.sidebar.text_input(
        "Symbols (comma-separated)",
        value="INFY,TCS,RELIANCE",
        help="NSE tickers; for indexes use NIFTY or BANKNIFTY.",
    )
    capital = st.sidebar.number_input("Starting capital (Rs)", value=200_000.0, step=10_000.0, min_value=1_000.0)
    quantity = st.sidebar.number_input("Default quantity", value=1, step=1, min_value=1)
    st.sidebar.markdown("**Risk controls**")
    max_pct = st.sidebar.slider("Max % capital per trade", 0.01, 1.0, 0.20, 0.01)
    sl = st.sidebar.number_input("Stop-loss %", value=0.02, step=0.005, format="%.3f")
    tp = st.sidebar.number_input("Take-profit %", value=0.04, step=0.005, format="%.3f")
    max_loss = st.sidebar.number_input("Max daily loss (Rs, 0=off)", value=0.0, step=500.0)
    respect_hours = st.sidebar.checkbox("Respect market hours (NSE 09:15–15:30 IST)", value=False)
    refresh = st.sidebar.slider("Auto-refresh (s)", 1, 30, 5)
    st.session_state["refresh"] = refresh

    app = _ensure_app()
    if app is None or not app.is_running:
        if st.sidebar.button("Start trading", type="primary", use_container_width=True):
            symbols = [s.strip().upper() for s in symbols_text.split(",") if s.strip()]
            if not symbols:
                st.sidebar.error("At least one symbol required.")
                return
            _start_app(
                strategy_name=strategy,
                symbols=symbols,
                capital=capital,
                quantity=int(quantity),
                feed=feed,
                max_pct=max_pct,
                sl=sl,
                tp=tp,
                max_loss=max_loss,
                respect_hours=respect_hours,
            )
            st.rerun()
    else:
        if st.sidebar.button("Stop trading", type="secondary", use_container_width=True):
            _stop_app()
            st.rerun()


def render_overview(app: TradingApp) -> None:
    snap = app.snapshot()
    perf = app.performance()
    cols = st.columns(5)
    cols[0].metric("Equity", f"₹{snap['equity']:,.2f}")
    cols[1].metric("Cash", f"₹{snap['cash']:,.2f}")
    cols[2].metric("Open positions value", f"₹{snap['positions_value']:,.2f}")
    cols[3].metric("Unrealized PnL", f"₹{snap['unrealized_pnl']:,.2f}")
    delta_color = "normal"
    cols[4].metric(
        "Total PnL",
        f"₹{snap['total_pnl']:,.2f}",
        delta=f"{perf.roi_pct:.3f}%",
        delta_color=delta_color,
    )
    if snap.get("risk_halted"):
        st.error("Trading halted by risk manager (daily loss limit hit).")


def render_positions(app: TradingApp) -> None:
    st.subheader("Open positions")
    pos = app.snapshot()["open_positions"]
    if pos:
        st.dataframe(pd.DataFrame(pos), use_container_width=True, hide_index=True)
    else:
        st.info("No open positions yet.")


def render_trades(app: TradingApp) -> None:
    st.subheader("Trade log")
    df = app.trades_df()
    if df.empty:
        st.info("No trades yet.")
        return
    st.dataframe(
        df[["timestamp", "symbol", "side", "quantity", "price", "brokerage", "strategy"]]
        .iloc[::-1]
        .reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )


def render_equity_curve(app: TradingApp) -> None:
    st.subheader("Equity curve")
    df = app.equity_df()
    if df.empty:
        st.info("Equity curve will populate after the first trade.")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["equity"], name="Equity"))
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["cash"], name="Cash", line={"dash": "dot"}))
    fig.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 0}, height=320)
    st.plotly_chart(fig, use_container_width=True)


def render_performance(app: TradingApp) -> None:
    st.subheader("Performance")
    perf = app.performance().to_dict()
    cols = st.columns(4)
    cols[0].metric("Trades (closed)", perf["trades"])
    cols[1].metric("Win rate", f"{perf['win_rate_pct']}%")
    cols[2].metric("Profit factor", str(perf["profit_factor"]))
    cols[3].metric("Max drawdown", f"{perf['max_drawdown_pct']}%")


def main() -> None:
    st.title("NSE Paper Trading Engine")
    st.caption("Live data → strategy → paper execution → portfolio + analytics, all in one event loop.")

    render_sidebar()

    app = _ensure_app()
    if app is None:
        st.info(
            "Configure a strategy in the sidebar and press **Start trading** to begin. "
            "The engine works without broker credentials using yfinance polling."
        )
        return

    render_overview(app)
    left, right = st.columns([2, 1])
    with left:
        render_equity_curve(app)
        render_trades(app)
    with right:
        render_positions(app)
        render_performance(app)

    if app.is_running:
        time.sleep(int(st.session_state.get("refresh", 5)))
        st.rerun()


if __name__ == "__main__":
    main()
