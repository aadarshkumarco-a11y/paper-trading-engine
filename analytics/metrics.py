"""Performance metrics: PnL, ROI, win-rate, drawdown, equity curve."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from execution_engine.orders import OrderSide, Trade
from portfolio.book import Portfolio


@dataclass
class PerformanceReport:
    initial_capital: float
    equity: float
    total_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    roi_pct: float
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    average_win: float
    average_loss: float
    profit_factor: float
    max_drawdown_pct: float
    brokerage_paid: float

    def to_dict(self) -> dict:
        return asdict(self)


def trades_dataframe(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(
            columns=["timestamp", "symbol", "side", "quantity", "price", "brokerage", "strategy"]
        )
    df = pd.DataFrame([t.to_dict() for t in trades])
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def equity_dataframe(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["timestamp", "cash", "positions_value", "equity"])
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def _round_trip_pnls(trades: list[Trade]) -> list[float]:
    """Reconstruct realized PnL per closed round-trip from a chronological trade log.

    A round trip closes when a position returns to zero. Both equity (long-only)
    and short flows are supported.
    """
    by_symbol: dict[str, list[Trade]] = {}
    for t in trades:
        by_symbol.setdefault(t.symbol, []).append(t)

    pnls: list[float] = []
    for symbol_trades in by_symbol.values():
        running_qty = 0
        running_cost = 0.0  # signed: long cost positive, short proceeds negative
        running_brokerage = 0.0
        for t in symbol_trades:
            signed_qty = t.side.sign * t.quantity
            new_qty = running_qty + signed_qty
            running_brokerage += t.brokerage

            if running_qty == 0 or (running_qty > 0) == (signed_qty > 0):
                # Opening / adding
                running_cost += signed_qty * t.price
                running_qty = new_qty
                continue

            # Reducing or closing
            closing_qty = min(abs(running_qty), abs(signed_qty))
            avg_entry = running_cost / running_qty if running_qty != 0 else 0.0
            if running_qty > 0:  # long → closing with sell
                pnl = (t.price - avg_entry) * closing_qty
            else:  # short → closing with buy
                pnl = (avg_entry - t.price) * closing_qty
            pnls.append(pnl - running_brokerage)
            running_brokerage = 0.0

            # Update running quantities/costs for the residual.
            running_qty = new_qty
            running_cost = 0.0 if running_qty == 0 else running_qty * t.price
        # Discard residual open positions; they are not realized.
    return pnls


def _max_drawdown(equity_curve: pd.Series) -> float:
    if equity_curve.empty:
        return 0.0
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    return float(drawdown.min())


def compute_performance(
    portfolio: Portfolio,
    trades: list[Trade],
    equity_rows: list[dict] | None = None,
) -> PerformanceReport:
    pnls = _round_trip_pnls(trades)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    n_trades = len(pnls)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    win_rate = (len(wins) / n_trades * 100.0) if n_trades else 0.0
    profit_factor = (
        sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf") if wins else 0.0
    )

    equity_df = equity_dataframe(equity_rows or [])
    max_dd = _max_drawdown(equity_df["equity"]) * 100 if not equity_df.empty else 0.0

    return PerformanceReport(
        initial_capital=round(portfolio.initial_capital, 2),
        equity=round(portfolio.equity(), 2),
        total_pnl=round(portfolio.total_pnl(), 2),
        realized_pnl=round(portfolio.realized_pnl(), 2),
        unrealized_pnl=round(portfolio.unrealized_pnl(), 2),
        roi_pct=round((portfolio.total_pnl() / portfolio.initial_capital) * 100, 4),
        trades=n_trades,
        wins=len(wins),
        losses=len(losses),
        win_rate_pct=round(win_rate, 2),
        average_win=round(avg_win, 2),
        average_loss=round(avg_loss, 2),
        profit_factor=round(profit_factor, 4) if profit_factor != float("inf") else profit_factor,
        max_drawdown_pct=round(max_dd, 4),
        brokerage_paid=round(portfolio.brokerage_paid, 2),
    )


# Re-export so analysers don't need to import from execution_engine directly.
__all__ = [
    "PerformanceReport",
    "compute_performance",
    "trades_dataframe",
    "equity_dataframe",
    "OrderSide",
]
