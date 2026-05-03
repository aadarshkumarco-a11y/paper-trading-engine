"""Indian market hour and expiry helpers (Asia/Kolkata)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def now_ist(reference: datetime | None = None) -> datetime:
    """Return the current time in IST. If `reference` is given (any tz), convert it."""
    if reference is None:
        return datetime.now(IST)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return reference.astimezone(IST)


def is_weekday(d: date) -> bool:
    return d.weekday() < 5


def is_market_open(reference: datetime | None = None) -> bool:
    """NSE cash/F&O regular session: Mon–Fri, 09:15–15:30 IST."""
    n = now_ist(reference)
    if not is_weekday(n.date()):
        return False
    return MARKET_OPEN <= n.time() <= MARKET_CLOSE


def next_market_open(reference: datetime | None = None) -> datetime:
    n = now_ist(reference)
    candidate = n.replace(hour=MARKET_OPEN.hour, minute=MARKET_OPEN.minute, second=0, microsecond=0)
    if n.time() >= MARKET_OPEN and is_weekday(n.date()):
        candidate = candidate + timedelta(days=1)
    while not is_weekday(candidate.date()):
        candidate += timedelta(days=1)
    return candidate


def next_weekly_expiry(reference: datetime | None = None, weekday: int = 3) -> date:
    """NIFTY weekly expiry is Thursday (weekday=3). BANKNIFTY also historically Thursday.
    If today is the expiry weekday and market is still open, return today's expiry.
    Otherwise return the next occurrence of `weekday`.
    """
    n = now_ist(reference)
    today = n.date()
    days_ahead = (weekday - today.weekday()) % 7
    if days_ahead == 0 and n.time() >= MARKET_CLOSE:
        days_ahead = 7
    return today + timedelta(days=days_ahead)
