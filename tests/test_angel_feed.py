"""Tests for the Angel SmartAPI adapter using a fully mocked SmartAPI module.

We can't (and shouldn't) hit the real broker in CI, so we patch
`SmartApi`, `SmartApi.smartWebSocketV2` and `pyotp` into `sys.modules`
before importing `AngelDataFeed`.
"""
from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock

import pytest

from data_feed.angel_symbol_master import AngelSymbolMaster


@pytest.fixture
def fake_smartapi(monkeypatch):
    smart_connect = MagicMock(name="SmartConnect")
    smart_connect_instance = MagicMock()
    smart_connect_instance.generateSession.return_value = {
        "status": True,
        "data": {
            "jwtToken": "JWT",
            "refreshToken": "REFRESH",
            "feedToken": "FEED",
        },
    }
    smart_connect_instance.getfeedToken.return_value = "FEED"
    smart_connect.return_value = smart_connect_instance

    smart_ws = MagicMock(name="SmartWebSocketV2")
    smart_ws_instance = MagicMock()
    smart_ws_instance.connect = MagicMock()
    smart_ws_instance.subscribe = MagicMock()
    smart_ws_instance.close_connection = MagicMock()
    smart_ws.return_value = smart_ws_instance

    smartapi_mod = types.ModuleType("SmartApi")
    smartapi_mod.SmartConnect = smart_connect
    smartws_mod = types.ModuleType("SmartApi.smartWebSocketV2")
    smartws_mod.SmartWebSocketV2 = smart_ws
    pyotp_mod = types.ModuleType("pyotp")
    totp_obj = MagicMock()
    totp_obj.now.return_value = "123456"
    pyotp_mod.TOTP = MagicMock(return_value=totp_obj)

    monkeypatch.setitem(sys.modules, "SmartApi", smartapi_mod)
    monkeypatch.setitem(sys.modules, "SmartApi.smartWebSocketV2", smartws_mod)
    monkeypatch.setitem(sys.modules, "pyotp", pyotp_mod)

    monkeypatch.setenv("ANGEL_API_KEY", "key")
    monkeypatch.setenv("ANGEL_CLIENT_CODE", "C123")
    monkeypatch.setenv("ANGEL_PASSWORD", "pin")
    monkeypatch.setenv("ANGEL_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    # Reset the cached settings so the new env vars take effect.
    from utils import config

    config.get_settings.cache_clear()
    yield {
        "SmartConnect": smart_connect,
        "smart_connect_instance": smart_connect_instance,
        "SmartWebSocketV2": smart_ws,
        "smart_ws_instance": smart_ws_instance,
        "pyotp": pyotp_mod,
    }
    config.get_settings.cache_clear()


def test_symbol_master_lookup(tmp_path):
    cache = tmp_path / "scrip.json"
    records = [
        {"token": "3045", "symbol": "SBIN-EQ", "name": "SBIN", "exch_seg": "NSE"},
        {"token": "11536", "symbol": "INFY-EQ", "name": "INFY", "exch_seg": "NSE"},
        {"token": "26009", "symbol": "BANKNIFTY", "name": "BANKNIFTY", "exch_seg": "NSE"},
    ]
    cache.write_text(json.dumps(records))
    master = AngelSymbolMaster(cache_path=cache)
    assert master.token_for("INFY", "NSE") == "11536"
    assert master.token_for("INFY-EQ", "NSE") == "11536"
    assert master.token_for("BANKNIFTY", "NSE") == "26009"
    assert master.token_for("UNKNOWN", "NSE") is None


def test_angel_login_and_subscribe(fake_smartapi, tmp_path):
    cache = tmp_path / "scrip.json"
    cache.write_text(json.dumps([
        {"token": "3045", "symbol": "SBIN-EQ", "name": "SBIN", "exch_seg": "NSE"},
        {"token": "11536", "symbol": "INFY-EQ", "name": "INFY", "exch_seg": "NSE"},
    ]))
    master = AngelSymbolMaster(cache_path=cache)
    from data_feed.angel_feed import AngelDataFeed

    feed = AngelDataFeed(symbol_master=master)
    feed.subscribe(["INFY", "SBIN"])
    feed.start()
    try:
        # Login was called with TOTP "123456".
        fake_smartapi["smart_connect_instance"].generateSession.assert_called_once_with(
            "C123", "pin", "123456"
        )
        # WebSocket constructed with the right credentials.
        fake_smartapi["SmartWebSocketV2"].assert_called_once_with("JWT", "key", "C123", "FEED")
        # Both tokens were registered.
        assert set(feed._symbol_to_token.values()) == {"3045", "11536"}
    finally:
        feed.stop()


def test_angel_tick_message_published(fake_smartapi, tmp_path):
    cache = tmp_path / "scrip.json"
    cache.write_text(json.dumps([
        {"token": "11536", "symbol": "INFY-EQ", "name": "INFY", "exch_seg": "NSE"},
    ]))
    master = AngelSymbolMaster(cache_path=cache)
    from data_feed.angel_feed import AngelDataFeed

    feed = AngelDataFeed(symbol_master=master)
    feed.subscribe(["INFY"])
    received: list = []
    feed.on_tick(received.append)
    feed.start()
    try:
        feed._handle_ws_message({
            "token": "11536",
            "last_traded_price": 150025,  # in paise => 1500.25
            "volume_trade_for_the_day": 1000,
        })
        assert received[0].symbol == "INFY"
        assert received[0].ltp == 1500.25
        assert received[0].volume == 1000
    finally:
        feed.stop()


def test_angel_tick_string_payload(fake_smartapi, tmp_path):
    cache = tmp_path / "scrip.json"
    cache.write_text(json.dumps([
        {"token": "11536", "symbol": "INFY-EQ", "name": "INFY", "exch_seg": "NSE"},
    ]))
    master = AngelSymbolMaster(cache_path=cache)
    from data_feed.angel_feed import AngelDataFeed

    feed = AngelDataFeed(symbol_master=master)
    feed.subscribe(["INFY"])
    received: list = []
    feed.on_tick(received.append)
    feed.start()
    try:
        feed._handle_ws_message(json.dumps({
            "token": "11536",
            "last_traded_price": 150025,
        }))
        assert received and received[0].ltp == 1500.25
    finally:
        feed.stop()


def test_angel_get_history_parses_candles(fake_smartapi, tmp_path):
    cache = tmp_path / "scrip.json"
    cache.write_text(json.dumps([
        {"token": "11536", "symbol": "INFY-EQ", "name": "INFY", "exch_seg": "NSE"},
    ]))
    master = AngelSymbolMaster(cache_path=cache)

    fake_smartapi["smart_connect_instance"].getCandleData.return_value = {
        "data": [
            ["2024-05-01T09:15:00+05:30", 1500.0, 1505.0, 1499.0, 1502.0, 12000],
            ["2024-05-01T09:20:00+05:30", 1502.0, 1510.0, 1501.0, 1508.0, 8000],
        ]
    }
    from data_feed.angel_feed import AngelDataFeed

    feed = AngelDataFeed(symbol_master=master)
    feed.login()
    df = feed.get_history("INFY", period="1d", interval="5m")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert df["close"].iloc[-1] == 1508.0
