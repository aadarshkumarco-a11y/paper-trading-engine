"""Simple brokerage cost models. Defaults approximate Zerodha equity intraday."""
from __future__ import annotations

from abc import ABC, abstractmethod

from execution_engine.orders import OrderSide


class BrokerageModel(ABC):
    @abstractmethod
    def charge(self, side: OrderSide, quantity: int, price: float) -> float:
        ...


class FlatBrokerage(BrokerageModel):
    def __init__(self, per_trade: float = 20.0) -> None:
        self.per_trade = float(per_trade)

    def charge(self, side: OrderSide, quantity: int, price: float) -> float:
        return self.per_trade


class ZerodhaEquityBrokerage(BrokerageModel):
    """Approximation of Zerodha equity intraday charges:
    brokerage = min(20, 0.03% of turnover)
    plus STT, exchange fees, GST and SEBI charges roughly bundled into a flat 0.03% adder.
    """

    def __init__(self, per_trade_cap: float = 20.0, brokerage_pct: float = 0.0003,
                 taxes_pct: float = 0.0003) -> None:
        self.per_trade_cap = float(per_trade_cap)
        self.brokerage_pct = float(brokerage_pct)
        self.taxes_pct = float(taxes_pct)

    def charge(self, side: OrderSide, quantity: int, price: float) -> float:
        turnover = abs(quantity) * abs(price)
        brokerage = min(self.per_trade_cap, turnover * self.brokerage_pct)
        taxes = turnover * self.taxes_pct
        return round(brokerage + taxes, 2)
