from datetime import datetime

from utils.market_hours import IST, is_market_open, next_market_open, next_weekly_expiry


def test_market_open_during_session():
    # Tuesday 11:00 IST
    ts = datetime(2024, 5, 7, 11, 0, tzinfo=IST)
    assert is_market_open(ts) is True


def test_market_closed_pre_open():
    ts = datetime(2024, 5, 7, 9, 0, tzinfo=IST)
    assert is_market_open(ts) is False


def test_market_closed_weekend():
    ts = datetime(2024, 5, 11, 11, 0, tzinfo=IST)  # Saturday
    assert is_market_open(ts) is False


def test_next_market_open_skips_weekend():
    ts = datetime(2024, 5, 11, 11, 0, tzinfo=IST)  # Saturday
    nxt = next_market_open(ts)
    assert nxt.weekday() == 0  # Monday
    assert nxt.hour == 9 and nxt.minute == 15


def test_next_weekly_expiry_thursday():
    ts = datetime(2024, 5, 7, 11, 0, tzinfo=IST)  # Tuesday
    expiry = next_weekly_expiry(ts)
    assert expiry.weekday() == 3  # Thursday
    assert (expiry - ts.date()).days == 2
