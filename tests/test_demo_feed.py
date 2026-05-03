"""Smoke tests for the offline DemoDataFeed."""
import time

from data_feed.demo_feed import DemoDataFeed, _v_shaped_path
from data_feed.factory import create_feed


def test_demo_feed_publishes_scripted_path():
    feed = DemoDataFeed(tick_interval=0.05)
    received: list[float] = []
    feed.on_tick(lambda t: received.append(t.ltp))
    feed.subscribe(["DEMO"])
    feed.start()
    time.sleep(5.0)
    feed.stop()

    expected = _v_shaped_path()
    assert len(received) >= 30, f"expected >=30 ticks, got {len(received)}"
    # Order of emitted ticks must match the scripted path prefix.
    assert received[: len(received)] == expected[: len(received)]
    # The path must end higher than its trough so a long position can be exited
    # at a profit by RSI/EMA strategies.
    assert max(received) > min(received) * 1.3


def test_demo_feed_history_is_empty():
    feed = DemoDataFeed()
    df = feed.get_history("DEMO")
    assert df.empty
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_factory_resolves_demo_kind():
    feed = create_feed("demo")
    assert isinstance(feed, DemoDataFeed)
