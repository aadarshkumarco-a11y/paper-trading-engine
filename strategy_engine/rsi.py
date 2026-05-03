"""Mean-reversion RSI strategy."""
from __future__ import annotations

from data_feed.base import Tick
from strategy_engine.base import Signal, SignalType, Strategy
from strategy_engine.indicators import rsi


class RSIStrategy(Strategy):
    """Buy when RSI dips below oversold; sell/exit when RSI rises above overbought."""

    name = "RSI"

    def __init__(
        self,
        symbols: list[str],
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        quantity: int = 1,
    ) -> None:
        super().__init__(symbols, quantity=quantity)
        self.period = int(period)
        self.oversold = float(oversold)
        self.overbought = float(overbought)
        self._in_position: dict[str, bool] = {s: False for s in self.symbols}

    def on_tick(self, tick: Tick) -> Signal | None:
        if tick.symbol not in self._in_position:
            return None
        self.context.update(tick)
        closes = self.context.closes(tick.symbol)
        if len(closes) < self.period + 1:
            return None
        latest = float(rsi(closes, self.period).iloc[-1])
        if latest <= self.oversold and not self._in_position[tick.symbol]:
            self._in_position[tick.symbol] = True
            return Signal(
                type=SignalType.BUY,
                symbol=tick.symbol,
                quantity=self.quantity,
                price=tick.ltp,
                reason=f"RSI {latest:.1f} <= {self.oversold}",
                metadata={"rsi": latest},
            )
        if latest >= self.overbought and self._in_position[tick.symbol]:
            self._in_position[tick.symbol] = False
            return Signal(
                type=SignalType.SELL,
                symbol=tick.symbol,
                quantity=self.quantity,
                price=tick.ltp,
                reason=f"RSI {latest:.1f} >= {self.overbought}",
                metadata={"rsi": latest},
            )
        return None
