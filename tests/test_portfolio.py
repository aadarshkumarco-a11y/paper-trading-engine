from datetime import datetime

from execution_engine.orders import OrderSide, Trade
from portfolio.book import Portfolio
from portfolio.storage import PortfolioStorage


def _trade(symbol, side, qty, price, brokerage=0.0):
    return Trade(
        order_id="x",
        symbol=symbol,
        side=side,
        quantity=qty,
        price=price,
        brokerage=brokerage,
        timestamp=datetime.now(),
    )


def test_buy_then_sell_realizes_pnl():
    p = Portfolio(initial_capital=100000.0)
    p.apply_trade(_trade("INFY", OrderSide.BUY, 10, 1500))
    p.apply_trade(_trade("INFY", OrderSide.SELL, 10, 1600))
    pos = p.position("INFY")
    assert pos.quantity == 0
    assert pos.realized_pnl == 1000.0
    assert p.cash == 100000.0 + 1000.0


def test_partial_close_keeps_avg_price():
    p = Portfolio(initial_capital=100000.0)
    p.apply_trade(_trade("INFY", OrderSide.BUY, 10, 1500))
    p.apply_trade(_trade("INFY", OrderSide.SELL, 4, 1700))
    pos = p.position("INFY")
    assert pos.quantity == 6
    assert pos.avg_price == 1500
    assert pos.realized_pnl == 800.0


def test_short_sell_then_cover():
    p = Portfolio(initial_capital=100000.0)
    p.apply_trade(_trade("INFY", OrderSide.SELL, 5, 1500))
    p.apply_trade(_trade("INFY", OrderSide.BUY, 5, 1400))
    pos = p.position("INFY")
    assert pos.quantity == 0
    assert pos.realized_pnl == 500.0


def test_unrealized_pnl_marks_to_market():
    p = Portfolio(initial_capital=50000.0)
    p.apply_trade(_trade("INFY", OrderSide.BUY, 10, 1500))
    p.mark_to_market("INFY", 1550.0)
    assert p.unrealized_pnl() == 500.0
    assert p.equity() == 50000.0 + 500.0


def test_brokerage_reduces_cash_and_equity():
    p = Portfolio(initial_capital=100000.0)
    p.apply_trade(_trade("INFY", OrderSide.BUY, 10, 1500, brokerage=20))
    assert p.cash == 100000.0 - 15000.0 - 20.0


def test_storage_roundtrip(tmp_db):
    storage = PortfolioStorage(tmp_db)
    session_id = storage.start_session(initial_capital=50000.0, strategy="RSI")
    p = Portfolio(initial_capital=50000.0, storage=storage, session_id=session_id)
    p.apply_trade(_trade("INFY", OrderSide.BUY, 1, 1500))
    p.apply_trade(_trade("INFY", OrderSide.SELL, 1, 1600))
    rows = storage.trades(session_id)
    assert len(rows) == 2
    eq_rows = storage.equity_curve(session_id)
    assert len(eq_rows) == 2
    storage.close()
