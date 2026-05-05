"""Plotly chart helpers used by the Streamlit dashboard."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from ui.theme import COLORS


def candlestick_with_indicators(
    ohlc: pd.DataFrame,
    *,
    symbol: str = "",
    show_ema_fast: int = 9,
    show_ema_slow: int = 21,
    show_rsi: bool = True,
    height: int = 460,
) -> go.Figure:
    """Build a dark candlestick chart with EMA overlays and a small RSI panel.

    Empty / sparse data is handled gracefully — we still return a valid Figure
    so the UI doesn't break before the first ticks arrive.
    """
    fig = go.Figure()

    if ohlc is None or ohlc.empty:
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=COLORS["bg"],
            plot_bgcolor=COLORS["bg_alt"],
            height=height,
            annotations=[
                {
                    "text": "Waiting for live ticks…",
                    "xref": "paper", "yref": "paper",
                    "x": 0.5, "y": 0.5,
                    "showarrow": False,
                    "font": {"color": COLORS["text_muted"], "size": 14},
                }
            ],
            margin={"l": 30, "r": 20, "t": 30, "b": 30},
        )
        return fig

    fig.add_trace(
        go.Candlestick(
            x=ohlc.index,
            open=ohlc["open"],
            high=ohlc["high"],
            low=ohlc["low"],
            close=ohlc["close"],
            name=symbol or "Price",
            increasing_line_color=COLORS["profit"],
            decreasing_line_color=COLORS["loss"],
            increasing_fillcolor="rgba(0,255,159,0.55)",
            decreasing_fillcolor="rgba(255,77,77,0.55)",
            line={"width": 1.2},
        )
    )

    closes = ohlc["close"]
    if show_ema_fast and len(closes) >= 2:
        ema_fast = closes.ewm(span=show_ema_fast, adjust=False).mean()
        fig.add_trace(
            go.Scatter(
                x=ohlc.index,
                y=ema_fast,
                mode="lines",
                name=f"EMA{show_ema_fast}",
                line={"color": COLORS["accent"], "width": 1.4},
            )
        )
    if show_ema_slow and len(closes) >= 2:
        ema_slow = closes.ewm(span=show_ema_slow, adjust=False).mean()
        fig.add_trace(
            go.Scatter(
                x=ohlc.index,
                y=ema_slow,
                mode="lines",
                name=f"EMA{show_ema_slow}",
                line={"color": "#f5a524", "width": 1.4, "dash": "dot"},
            )
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg_alt"],
        height=height,
        margin={"l": 40, "r": 20, "t": 40, "b": 30},
        showlegend=True,
        legend={
            "orientation": "h", "yanchor": "bottom", "y": 1.02,
            "xanchor": "right", "x": 1,
            "font": {"color": COLORS["text"]},
        },
        xaxis={
            "rangeslider": {"visible": False},
            "gridcolor": "rgba(255,255,255,0.05)",
            "showspikes": True,
            "spikemode": "across",
            "spikedash": "dot",
            "spikecolor": "rgba(255,255,255,0.25)",
        },
        yaxis={
            "gridcolor": "rgba(255,255,255,0.05)",
            "tickformat": ".2f",
        },
        hoverlabel={"bgcolor": "rgba(13,17,23,0.95)", "font": {"color": COLORS["text"]}},
    )
    if symbol:
        fig.update_layout(title={
            "text": f"{symbol}", "x": 0.01, "y": 0.97,
            "font": {"color": COLORS["text"], "size": 16},
        })
    return fig


def equity_curve_chart(equity_df: pd.DataFrame, *, height: int = 280) -> go.Figure:
    """Plot equity + cash over time with the dark theme."""
    fig = go.Figure()
    if equity_df is not None and not equity_df.empty:
        if "equity" in equity_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=equity_df.index,
                    y=equity_df["equity"],
                    name="Equity",
                    mode="lines",
                    line={"color": COLORS["profit"], "width": 2},
                    fill="tozeroy",
                    fillcolor="rgba(0,255,159,0.07)",
                )
            )
        if "cash" in equity_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=equity_df.index,
                    y=equity_df["cash"],
                    name="Cash",
                    mode="lines",
                    line={"color": COLORS["accent"], "width": 1.4, "dash": "dot"},
                )
            )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg_alt"],
        height=height,
        margin={"l": 40, "r": 20, "t": 24, "b": 30},
        showlegend=True,
        legend={
            "orientation": "h", "yanchor": "bottom", "y": 1.02,
            "xanchor": "right", "x": 1,
            "font": {"color": COLORS["text"]},
        },
        xaxis={"gridcolor": "rgba(255,255,255,0.05)"},
        yaxis={"gridcolor": "rgba(255,255,255,0.05)", "tickformat": ",.0f"},
    )
    return fig
