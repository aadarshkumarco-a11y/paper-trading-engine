from datetime import datetime

from execution_engine.orders import OrderSide, Trade
from portfolio.book import Portfolio
from portfolio.risk import RiskConfig, RiskManager
from strategy_engine.base import Signal, SignalType


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


def test_caps_quantity_to_capital():
    p = Portfolio(initial_capital=100000.0)
    rm = RiskManager(p, RiskConfig(max_capital_pct_per_trade=0.10))
    sig = Signal(type=SignalType.BUY, symbol="INFY", quantity=100)
    decision = rm.evaluate_signal(sig, last_price=1000.0)
    assert decision.allow is True
    # 10% of 100k = 10k, /1000 per share = 10 shares max.
    assert decision.quantity == 10


def test_rejects_short_when_disabled():
    p = Portfolio(initial_capital=100000.0)
    rm = RiskManager(p, RiskConfig(allow_short=False))
    sig = Signal(type=SignalType.SELL, symbol="INFY", quantity=5)
    decision = rm.evaluate_signal(sig, last_price=1000.0)
    assert decision.allow is False


def test_clamps_sell_to_position_size():
    p = Portfolio(initial_capital=100000.0)
    p.apply_trade(_trade("INFY", OrderSide.BUY, 5, 1500))
    rm = RiskManager(p, RiskConfig())
    sig = Signal(type=SignalType.SELL, symbol="INFY", quantity=20)
    decision = rm.evaluate_signal(sig, last_price=1500.0)
    assert decision.allow is True
    assert decision.quantity == 5


def test_stop_loss_triggers_exit():
    p = Portfolio(initial_capital=100000.0)
    p.apply_trade(_trade("INFY", OrderSide.BUY, 10, 1000))
    rm = RiskManager(p, RiskConfig(stop_loss_pct=0.02, take_profit_pct=None))
    exit_sig = rm.check_exits("INFY", 970)  # -3%
    assert exit_sig is not None
    assert exit_sig.type is SignalType.EXIT
    assert exit_sig.quantity == 10


def test_take_profit_triggers_exit():
    p = Portfolio(initial_capital=100000.0)
    p.apply_trade(_trade("INFY", OrderSide.BUY, 10, 1000))
    rm = RiskManager(p, RiskConfig(stop_loss_pct=None, take_profit_pct=0.04))
    exit_sig = rm.check_exits("INFY", 1050)  # +5%
    assert exit_sig is not None
    assert exit_sig.type is SignalType.EXIT


def test_daily_loss_halts_trading():
    p = Portfolio(initial_capital=100000.0)
    rm = RiskManager(p, RiskConfig(max_daily_loss=500))
    p.on_trade(rm.on_trade)
    # Realize a loss > 500.
    p.apply_trade(_trade("INFY", OrderSide.BUY, 10, 1000))
    p.apply_trade(_trade("INFY", OrderSide.SELL, 10, 940))
    assert rm.is_halted() is True
    decision = rm.evaluate_signal(
        Signal(type=SignalType.BUY, symbol="INFY", quantity=1), last_price=900.0
    )
    assert decision.allow is False
    assert decision.halt is True
