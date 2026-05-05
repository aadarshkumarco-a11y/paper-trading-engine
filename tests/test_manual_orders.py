"""Tests for the manual order / engine-only mode of TradingApp."""
from __future__ import annotations

import pytest

from engine import EngineConfig, TradingApp
from execution_engine.orders import OrderSide, OrderType


@pytest.fixture
def fake_feed_factory(monkeypatch, fake_feed):
    """Patch create_feed() to return our FakeDataFeed for engine_only tests."""
    feed = fake_feed
    monkeypatch.setattr("engine.create_feed", lambda *_args, **_kwargs: feed)
    return feed


def test_engine_only_starts_feed_with_symbols(tmp_path, fake_feed_factory):
    app = TradingApp(EngineConfig(
        initial_capital=100_000.0,
        db_path=str(tmp_path / "test.db"),
    ))
    app.start_engine_only(symbols=["INFY", "TCS"])
    try:
        assert app.is_engine_running
        assert app.is_running is False  # no strategy
        assert app.watchlist() == ["INFY", "TCS"]
    finally:
        app.stop()
    assert not app.is_engine_running


def test_manual_market_buy_updates_portfolio(tmp_path, fake_feed_factory):
    feed = fake_feed_factory
    app = TradingApp(EngineConfig(
        initial_capital=100_000.0,
        slippage_pct=0.0,
        latency_ms=0,
        db_path=str(tmp_path / "test.db"),
    ))
    app.start_engine_only(symbols=["INFY"])
    feed.push("INFY", 1500.0)
    try:
        order = app.place_manual_order("INFY", OrderSide.BUY, quantity=10)
        assert order.symbol == "INFY"
        pos = app.portfolio.position("INFY")
        assert pos is not None
        assert pos.quantity == 10
        assert pos.avg_price == pytest.approx(1500.0, rel=1e-3)
        assert app.portfolio.cash < 100_000.0  # cash was spent
    finally:
        app.stop()


def test_manual_sell_after_buy_realises_pnl(tmp_path, fake_feed_factory):
    feed = fake_feed_factory
    app = TradingApp(EngineConfig(
        initial_capital=100_000.0,
        slippage_pct=0.0,
        latency_ms=0,
        db_path=str(tmp_path / "test.db"),
    ))
    app.start_engine_only(symbols=["DEMO"])
    feed.push("DEMO", 100.0)
    try:
        app.place_manual_order("DEMO", OrderSide.BUY, 5)
        feed.push("DEMO", 110.0)
        app.place_manual_order("DEMO", OrderSide.SELL, 5)
        pos = app.portfolio.position("DEMO")
        assert pos is not None
        assert pos.quantity == 0
        assert pos.realized_pnl == pytest.approx(50.0, rel=0.05)  # (110-100)*5 minus brokerage
    finally:
        app.stop()


def test_manual_order_rejects_invalid_quantity(tmp_path, fake_feed_factory):
    feed = fake_feed_factory
    app = TradingApp(EngineConfig(
        initial_capital=100_000.0,
        db_path=str(tmp_path / "test.db"),
    ))
    app.start_engine_only(symbols=["INFY"])
    feed.push("INFY", 100.0)
    try:
        with pytest.raises(ValueError, match="positive"):
            app.place_manual_order("INFY", OrderSide.BUY, 0)
        with pytest.raises(ValueError, match="Symbol"):
            app.place_manual_order("", OrderSide.BUY, 1)
    finally:
        app.stop()


def test_manual_limit_order_requires_limit_price(tmp_path, fake_feed_factory):
    feed = fake_feed_factory
    app = TradingApp(EngineConfig(
        initial_capital=100_000.0,
        db_path=str(tmp_path / "test.db"),
    ))
    app.start_engine_only(symbols=["INFY"])
    feed.push("INFY", 100.0)
    try:
        with pytest.raises(ValueError, match="limit_price"):
            app.place_manual_order(
                "INFY", OrderSide.BUY, 1, order_type=OrderType.LIMIT, limit_price=None,
            )
    finally:
        app.stop()


def test_add_remove_symbol_updates_watchlist(tmp_path, fake_feed_factory):
    app = TradingApp(EngineConfig(
        initial_capital=50_000.0,
        db_path=str(tmp_path / "test.db"),
    ))
    app.add_symbol("INFY")
    app.add_symbol("infy")  # case-insensitive de-dup
    app.add_symbol("TCS")
    assert app.watchlist() == ["INFY", "TCS"]
    app.remove_symbol("INFY")
    assert app.watchlist() == ["TCS"]


def test_market_status_includes_open_flag_and_clock(tmp_path, fake_feed_factory):
    app = TradingApp(EngineConfig(
        initial_capital=10_000.0,
        db_path=str(tmp_path / "test.db"),
    ))
    status = app.market_status()
    assert "open" in status and isinstance(status["open"], bool)
    assert "now_ist" in status and "IST" not in status["now_ist"]
