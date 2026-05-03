"""Options helpers: ATM strike selection, weekly expiry, CE/PE handling."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from data_feed.nse_option_chain import NSEOptionChain, OptionContract
from utils.market_hours import next_weekly_expiry


@dataclass
class SelectedOption:
    underlying: str
    strike: float
    expiry: str
    option_type: str
    contract: OptionContract


def select_atm_option(
    chain_client: NSEOptionChain,
    underlying: str,
    option_type: str,
    expiry: str | None = None,
    offset: int = 0,
) -> SelectedOption | None:
    """Return the ATM (or ATM+offset×step) option for `underlying` on `expiry`.

    `offset` is in strike steps (e.g. for NIFTY, +1 == 50 points OTM for CE).
    If `expiry` is omitted, the next available weekly expiry is used.
    """
    option_type = option_type.upper()
    if option_type not in {"CE", "PE"}:
        raise ValueError("option_type must be CE or PE")

    if expiry is None:
        expiries = chain_client.get_expiries(underlying) or []
        target = next_weekly_expiry().strftime("%d-%b-%Y").upper()
        # NSE expiry format is e.g. "30-MAY-2024"; pick the closest >= target if possible.
        expiry = next((e for e in expiries if e.upper() >= target), expiries[0] if expiries else None)
        if expiry is None:
            return None

    atm = chain_client.get_atm_strike(underlying)
    if atm is None:
        return None
    step = chain_client._strike_step(underlying)
    target_strike = atm + offset * step

    chain = chain_client.get_chain(underlying, expiry=expiry)
    if not chain:
        return None
    candidates = [c for c in chain if c.option_type == option_type]
    if not candidates:
        return None
    best = min(candidates, key=lambda c: abs(c.strike - target_strike))
    return SelectedOption(
        underlying=underlying,
        strike=best.strike,
        expiry=best.expiry,
        option_type=option_type,
        contract=best,
    )


def days_to_expiry(expiry_str: str, reference: datetime | date | None = None) -> int | None:
    parsed = NSEOptionChain.parse_expiry(expiry_str)
    if parsed is None:
        return None
    if reference is None:
        reference = datetime.now()
    if isinstance(reference, datetime):
        reference = reference.date()
    return max(0, (parsed.date() - reference).days)
