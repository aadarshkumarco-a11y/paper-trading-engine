"""EMA crossover strategy: long fast EMA above slow EMA."""
from __future__ import annotations

from data_feed.base import Tick
from strategy_engine.base import Signal, SignalType, Strategy
from strategy_engine.indicators import ema


class EMACrossoverStrategy(Strategy):
    name = "EMA Crossover"

    def __init__(
        self,
        symbols: list[str],
        fast: int = 9,
        slow: int = 21,
        quantity: int = 1,
    ) -> None:
        if fast >= slow:
            raise ValueError("fast period must be smaller than slow period")
        super().__init__(symbols, quantity=quantity)
        self.fast = int(fast)
        self.slow = int(slow)
        self._last_state: dict[str, int] = {}  # 1 fast above slow, -1 below
        self._in_position: dict[str, bool] = {s: False for s in self.symbols}

    def on_tick(self, tick: Tick) -> Signal | None:
        if tick.symbol not in self._in_position:
            return None
        self.context.update(tick)
        closes = self.context.closes(tick.symbol)
        if len(closes) < self.slow + 1:
            return None
        fast_val = float(ema(closes, self.fast).iloc[-1])
        slow_val = float(ema(closes, self.slow).iloc[-1])
        state = 1 if fast_val > slow_val else -1
        prev = self._last_state.get(tick.symbol)
        self._last_state[tick.symbol] = state
        if prev is None or prev == state:
            return None
        if state == 1 and not self._in_position[tick.symbol]:
            self._in_position[tick.symbol] = True
            return Signal(
                type=SignalType.BUY,
                symbol=tick.symbol,
                quantity=self.quantity,
                price=tick.ltp,
                reason=f"EMA{self.fast}({fast_val:.2f}) crossed above EMA{self.slow}({slow_val:.2f})",
                metadata={"fast": fast_val, "slow": slow_val},
            )
        if state == -1 and self._in_position[tick.symbol]:
            self._in_position[tick.symbol] = False
            return Signal(
                type=SignalType.SELL,
                symbol=tick.symbol,
                quantity=self.quantity,
                price=tick.ltp,
                reason=f"EMA{self.fast}({fast_val:.2f}) crossed below EMA{self.slow}({slow_val:.2f})",
                metadata={"fast": fast_val, "slow": slow_val},
            )
        return None
