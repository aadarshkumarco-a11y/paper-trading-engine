"""Example custom strategy.

Run with:
    python main.py --custom examples/custom_strategy.py:MeanReversion --symbols INFY
"""
from __future__ import annotations

from data_feed.base import Tick
from strategy_engine.base import Signal, SignalType, Strategy
from strategy_engine.indicators import sma


class MeanReversion(Strategy):
    """Buy when price is `entry_z` standard deviations below the SMA, exit at the SMA."""

    name = "MeanReversion"

    def __init__(
        self,
        symbols: list[str],
        period: int = 20,
        entry_z: float = 1.5,
        quantity: int = 1,
    ) -> None:
        super().__init__(symbols, quantity=quantity)
        self.period = int(period)
        self.entry_z = float(entry_z)
        self._in_position: dict[str, bool] = {s: False for s in symbols}

    def on_tick(self, tick: Tick) -> Signal | None:
        if tick.symbol not in self._in_position:
            return None
        self.context.update(tick)
        closes = self.context.closes(tick.symbol)
        if len(closes) < self.period + 1:
            return None
        mean = float(sma(closes, self.period).iloc[-1])
        std = float(closes.iloc[-self.period:].std() or 0.0)
        if std == 0:
            return None
        z = (tick.ltp - mean) / std

        if not self._in_position[tick.symbol] and z <= -self.entry_z:
            self._in_position[tick.symbol] = True
            return Signal(
                type=SignalType.BUY,
                symbol=tick.symbol,
                quantity=self.quantity,
                price=tick.ltp,
                reason=f"z={z:.2f} <= -{self.entry_z}",
                metadata={"z": z, "mean": mean, "std": std},
            )
        if self._in_position[tick.symbol] and tick.ltp >= mean:
            self._in_position[tick.symbol] = False
            return Signal(
                type=SignalType.SELL,
                symbol=tick.symbol,
                quantity=self.quantity,
                price=tick.ltp,
                reason=f"reverted to mean ({mean:.2f})",
                metadata={"mean": mean},
            )
        return None
