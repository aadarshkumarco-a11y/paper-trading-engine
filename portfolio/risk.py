"""Risk management: stop-loss, take-profit, capital and daily-loss caps."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date

from execution_engine.orders import OrderSide, Trade
from portfolio.book import Portfolio
from strategy_engine.base import Signal, SignalType
from utils.logger import get_logger
from utils.market_hours import IST, now_ist


@dataclass
class RiskConfig:
    max_capital_pct_per_trade: float = 0.20  # max fraction of equity per single trade
    max_position_value: float | None = None  # absolute cap (Rs); overrides percentage if smaller
    max_daily_loss: float | None = None  # absolute Rs loss before halting
    stop_loss_pct: float | None = 0.02  # 2% adverse move closes long
    take_profit_pct: float | None = 0.04  # 4% favorable move closes long
    allow_short: bool = False


@dataclass
class _DailyState:
    day: date
    realized_pnl: float = 0.0
    halted: bool = False


@dataclass
class RiskDecision:
    allow: bool
    quantity: int
    reason: str = ""
    halt: bool = False


class RiskManager:
    """Filters signals and watches for SL/TP exits.

    Use `evaluate_signal(signal, last_price)` to clamp / reject incoming signals
    and `check_exits(symbol, last_price)` on every tick to fire stop-loss /
    take-profit exits.
    """

    def __init__(self, portfolio: Portfolio, config: RiskConfig | None = None) -> None:
        self.portfolio = portfolio
        self.config = config or RiskConfig()
        self.logger = get_logger("RiskManager")
        self._lock = threading.RLock()
        self._daily = _DailyState(day=now_ist().date())
        self._last_realized_per_symbol: dict[str, float] = {}

    # ----- core API -----
    def evaluate_signal(self, signal: Signal, last_price: float) -> RiskDecision:
        with self._lock:
            self._refresh_daily()
            if self._daily.halted:
                return RiskDecision(False, 0, "Daily-loss limit hit; trading halted", halt=True)
            if signal.type is SignalType.HOLD:
                return RiskDecision(False, 0, "HOLD")
            if signal.quantity <= 0:
                return RiskDecision(False, 0, "Non-positive quantity")
            if signal.type is SignalType.SELL and not self.config.allow_short:
                pos = self.portfolio.position(signal.symbol)
                if pos is None or pos.quantity <= 0:
                    return RiskDecision(False, 0, "Short selling disabled and no long position to close")
                qty = min(signal.quantity, pos.quantity)
                return RiskDecision(True, qty, "Closing long")
            if signal.type is SignalType.EXIT:
                pos = self.portfolio.position(signal.symbol)
                if pos is None or pos.quantity == 0:
                    return RiskDecision(False, 0, "No open position to exit")
                return RiskDecision(True, abs(pos.quantity), "Exit existing position")

            # BUY (or SELL when shorting allowed).
            equity = self.portfolio.equity()
            cap_pct = max(0.0, min(1.0, self.config.max_capital_pct_per_trade))
            cap_value = equity * cap_pct
            if self.config.max_position_value is not None:
                cap_value = min(cap_value, self.config.max_position_value)
            if cap_value <= 0 or last_price <= 0:
                return RiskDecision(False, 0, "Invalid capital cap or price")
            max_qty = int(cap_value // last_price)
            if max_qty <= 0:
                return RiskDecision(False, 0, "Trade exceeds capital allocation")
            qty = min(signal.quantity, max_qty)

            if signal.type is SignalType.BUY:
                cost = qty * last_price
                if cost > self.portfolio.cash:
                    qty = int(self.portfolio.cash // last_price)
                    if qty <= 0:
                        return RiskDecision(False, 0, "Insufficient cash")
            return RiskDecision(True, qty, "OK")

    def check_exits(self, symbol: str, last_price: float) -> Signal | None:
        if self.config.stop_loss_pct is None and self.config.take_profit_pct is None:
            return None
        pos = self.portfolio.position(symbol)
        if pos is None or pos.quantity == 0:
            return None
        change = (last_price - pos.avg_price) / pos.avg_price
        if pos.quantity < 0:
            change = -change
        if self.config.stop_loss_pct is not None and change <= -abs(self.config.stop_loss_pct):
            return Signal(
                type=SignalType.EXIT,
                symbol=symbol,
                quantity=abs(pos.quantity),
                price=last_price,
                reason=f"Stop-loss ({change*100:.2f}%)",
                metadata={"sl": self.config.stop_loss_pct},
            )
        if self.config.take_profit_pct is not None and change >= abs(self.config.take_profit_pct):
            return Signal(
                type=SignalType.EXIT,
                symbol=symbol,
                quantity=abs(pos.quantity),
                price=last_price,
                reason=f"Take-profit ({change*100:.2f}%)",
                metadata={"tp": self.config.take_profit_pct},
            )
        return None

    # ----- realised pnl tracking -----
    def on_trade(self, trade: Trade) -> None:
        """Listener: portfolio publishes trades here so we can track daily PnL."""
        with self._lock:
            self._refresh_daily()
            pos = self.portfolio.position(trade.symbol)
            new_realized = pos.realized_pnl if pos else 0.0
            prev = self._last_realized_per_symbol.get(trade.symbol, 0.0)
            delta = new_realized - prev - trade.brokerage
            self._last_realized_per_symbol[trade.symbol] = new_realized
            self._daily.realized_pnl += delta
            if (
                self.config.max_daily_loss is not None
                and self._daily.realized_pnl <= -abs(self.config.max_daily_loss)
            ):
                self._daily.halted = True
                self.logger.warning(
                    "Daily-loss limit hit (realized %.2f). Trading halted for %s.",
                    self._daily.realized_pnl, self._daily.day,
                )

    def is_halted(self) -> bool:
        with self._lock:
            self._refresh_daily()
            return self._daily.halted

    def daily_realized_pnl(self) -> float:
        with self._lock:
            self._refresh_daily()
            return self._daily.realized_pnl

    def _refresh_daily(self) -> None:
        today = now_ist().date()
        if today != self._daily.day:
            self._daily = _DailyState(day=today)
            self._last_realized_per_symbol.clear()


# Side-imports to avoid circular reference for type hints
__all__ = ["RiskConfig", "RiskDecision", "RiskManager", "OrderSide", "IST"]
