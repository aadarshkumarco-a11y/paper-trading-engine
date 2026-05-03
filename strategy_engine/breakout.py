"""Donchian-style breakout strategy."""
from __future__ import annotations

from data_feed.base import Tick
from strategy_engine.base import Signal, SignalType, Strategy


class BreakoutStrategy(Strategy):
    name = "Breakout"

    def __init__(
        self,
        symbols: list[str],
        lookback: int = 20,
        quantity: int = 1,
    ) -> None:
        super().__init__(symbols, quantity=quantity)
        self.lookback = int(lookback)
        self._in_position: dict[str, bool] = {s: False for s in self.symbols}

    def on_tick(self, tick: Tick) -> Signal | None:
        if tick.symbol not in self._in_position:
            return None
        self.context.update(tick)
        highs = self.context.highs(tick.symbol)
        lows = self.context.lows(tick.symbol)
        if len(highs) < self.lookback + 1:
            return None
        # Use the prior `lookback` bars (excluding current) to set the channel.
        prior_high = float(highs.iloc[-(self.lookback + 1):-1].max())
        prior_low = float(lows.iloc[-(self.lookback + 1):-1].min())
        if tick.ltp > prior_high and not self._in_position[tick.symbol]:
            self._in_position[tick.symbol] = True
            return Signal(
                type=SignalType.BUY,
                symbol=tick.symbol,
                quantity=self.quantity,
                price=tick.ltp,
                reason=f"Breakout above {prior_high:.2f}",
                metadata={"prior_high": prior_high, "prior_low": prior_low},
            )
        if tick.ltp < prior_low and self._in_position[tick.symbol]:
            self._in_position[tick.symbol] = False
            return Signal(
                type=SignalType.SELL,
                symbol=tick.symbol,
                quantity=self.quantity,
                price=tick.ltp,
                reason=f"Breakdown below {prior_low:.2f}",
                metadata={"prior_high": prior_high, "prior_low": prior_low},
            )
        return None
