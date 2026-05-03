from datetime import datetime, timedelta

from analytics.metrics import compute_performance, trades_dataframe
from execution_engine.orders import OrderSide, Trade
from portfolio.book import Portfolio


def _trade(symbol, side, qty, price, ts, brokerage=0.0):
    return Trade(
        order_id="x",
        symbol=symbol,
        side=side,
        quantity=qty,
        price=price,
        brokerage=brokerage,
        timestamp=ts,
    )


def test_performance_report_basic():
    p = Portfolio(initial_capital=100000.0)
    t0 = datetime(2024, 5, 1, 10)
    trades = [
        _trade("INFY", OrderSide.BUY, 10, 1500, t0, 10),
        _trade("INFY", OrderSide.SELL, 10, 1600, t0 + timedelta(minutes=30), 10),
        _trade("TCS", OrderSide.BUY, 5, 4000, t0 + timedelta(hours=1), 10),
        _trade("TCS", OrderSide.SELL, 5, 3950, t0 + timedelta(hours=2), 10),
    ]
    for t in trades:
        p.apply_trade(t)
    report = compute_performance(p, trades, equity_rows=[])
    assert report.trades == 2
    assert report.wins == 1
    assert report.losses == 1
    assert report.win_rate_pct == 50.0
    # +1000 win minus brokerage on close - matches our offsets approximately
    assert report.total_pnl == round(p.total_pnl(), 2)


def test_trades_dataframe_sorted():
    t0 = datetime(2024, 5, 1, 10)
    trades = [
        _trade("INFY", OrderSide.BUY, 1, 1500, t0 + timedelta(minutes=5)),
        _trade("INFY", OrderSide.SELL, 1, 1600, t0),
    ]
    df = trades_dataframe(trades)
    assert list(df["price"]) == [1600, 1500]


def test_empty_performance():
    p = Portfolio(initial_capital=10000.0)
    report = compute_performance(p, trades=[], equity_rows=[])
    assert report.trades == 0
    assert report.wins == 0
    assert report.losses == 0
    assert report.total_pnl == 0
