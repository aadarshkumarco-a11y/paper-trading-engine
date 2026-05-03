import random

import pytest

from execution_engine.brokerage import FlatBrokerage
from execution_engine.engine import ExecutionEngine
from execution_engine.orders import Order, OrderSide, OrderStatus, OrderType


def _make_engine(feed, **kwargs):
    return ExecutionEngine(
        feed,
        brokerage=FlatBrokerage(per_trade=10.0),
        slippage_pct=0.0,
        latency_ms=0,
        rng=random.Random(0),
        **kwargs,
    )


def test_market_order_fills_at_last_price(fake_feed):
    engine = _make_engine(fake_feed)
    fills = []
    engine.on_trade(lambda trade, _order: fills.append(trade))
    fake_feed.push("INFY", 1500.0)

    o = Order(symbol="INFY", side=OrderSide.BUY, quantity=10, order_type=OrderType.MARKET)
    engine.submit(o)

    assert o.status is OrderStatus.FILLED
    assert o.fill_price == pytest.approx(1500.0)
    assert len(fills) == 1
    assert fills[0].brokerage == 10.0


def test_market_order_rejected_without_price(fake_feed):
    engine = _make_engine(fake_feed)
    rejects = []
    engine.on_reject(rejects.append)
    o = Order(symbol="UNKNOWN", side=OrderSide.BUY, quantity=1, order_type=OrderType.MARKET)
    engine.submit(o)
    assert o.status is OrderStatus.REJECTED
    assert rejects == [o]


def test_limit_buy_waits_for_price_to_drop(fake_feed):
    engine = _make_engine(fake_feed)
    fills = []
    engine.on_trade(lambda trade, _order: fills.append(trade))
    fake_feed.push("INFY", 1500.0)

    o = Order(
        symbol="INFY", side=OrderSide.BUY, quantity=5,
        order_type=OrderType.LIMIT, limit_price=1450.0,
    )
    engine.submit(o)
    assert o.status is OrderStatus.PENDING
    fake_feed.push("INFY", 1460.0)  # above limit, no fill yet
    assert o.status is OrderStatus.PENDING
    fake_feed.push("INFY", 1440.0)
    assert o.status is OrderStatus.FILLED
    assert o.fill_price == 1450.0
    assert fills[0].price == 1450.0


def test_limit_order_can_be_cancelled(fake_feed):
    engine = _make_engine(fake_feed)
    fake_feed.push("INFY", 1500.0)
    o = Order(
        symbol="INFY", side=OrderSide.BUY, quantity=5,
        order_type=OrderType.LIMIT, limit_price=1400.0,
    )
    engine.submit(o)
    assert engine.cancel(o.id) is True
    assert o.status is OrderStatus.CANCELLED


def test_slippage_makes_market_buy_more_expensive(fake_feed):
    engine = ExecutionEngine(
        fake_feed,
        brokerage=FlatBrokerage(per_trade=0),
        slippage_pct=0.01,
        latency_ms=0,
        rng=random.Random(42),
    )
    fake_feed.push("INFY", 1000.0)
    o = Order(symbol="INFY", side=OrderSide.BUY, quantity=1, order_type=OrderType.MARKET)
    engine.submit(o)
    assert o.fill_price >= 1000.0


def test_invalid_quantity_raises():
    with pytest.raises(ValueError):
        Order(symbol="INFY", side=OrderSide.BUY, quantity=0)


def test_limit_without_price_raises():
    with pytest.raises(ValueError):
        Order(symbol="INFY", side=OrderSide.BUY, quantity=1, order_type=OrderType.LIMIT)
