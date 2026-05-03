"""High-level wiring used by the CLI and Streamlit UI."""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

import pandas as pd

from analytics.metrics import (
    PerformanceReport,
    compute_performance,
    equity_dataframe,
    trades_dataframe,
)
from data_feed.base import DataFeed, Tick
from data_feed.factory import create_feed
from execution_engine.brokerage import BrokerageModel, ZerodhaEquityBrokerage
from execution_engine.engine import ExecutionEngine
from execution_engine.event_loop import TradingEventLoop
from execution_engine.orders import Order, OrderSide, OrderStatus, OrderType, Trade
from portfolio.book import Portfolio
from portfolio.risk import RiskConfig, RiskManager
from portfolio.storage import PortfolioStorage
from strategy_engine.base import Strategy
from utils.config import get_settings
from utils.logger import get_logger
from utils.market_hours import now_ist


@dataclass
class EngineConfig:
    initial_capital: float = 100_000.0
    feed: str | None = None  # yfinance | kite | angel
    slippage_pct: float = 0.0005
    latency_ms: int = 50
    respect_market_hours: bool = False
    risk: RiskConfig | None = None
    db_path: str | None = None


class TradingApp:
    """Owns the data feed, execution engine, portfolio, risk manager and event loop.

    Use as:
        app = TradingApp(config)
        app.set_strategy(RSIStrategy(["INFY"]))
        app.start()
        ...
        app.stop()
    """

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        self.logger = get_logger("TradingApp")
        settings = get_settings()
        db_path = self.config.db_path or settings.db_path
        self.storage = PortfolioStorage(db_path)
        self.session_id = self.storage.start_session(
            initial_capital=self.config.initial_capital,
            strategy="(unset)",
        )
        self.portfolio = Portfolio(
            initial_capital=self.config.initial_capital,
            storage=self.storage,
            session_id=self.session_id,
        )
        self.feed: DataFeed = create_feed(self.config.feed)
        self.brokerage: BrokerageModel = ZerodhaEquityBrokerage()
        self.execution = ExecutionEngine(
            self.feed,
            brokerage=self.brokerage,
            slippage_pct=self.config.slippage_pct,
            latency_ms=self.config.latency_ms,
        )
        self.risk = RiskManager(self.portfolio, self.config.risk)
        self.strategy: Strategy | None = None
        self.loop: TradingEventLoop | None = None
        self._lock = threading.RLock()
        self._trade_log: list[Trade] = []
        self._tick_history: dict[str, deque[Tick]] = {}
        self._tick_history_max = 5000
        self._symbols: set[str] = set()
        self._engine_only_running = False
        self.portfolio.on_trade(self._capture_trade)
        # When no strategy is loaded we still need ticks → portfolio (for
        # manual orders). The event loop also wires this; we avoid double
        # apply by only registering it via the loop when a strategy is set.
        self.feed.on_tick(self._capture_tick)
        self.execution.on_trade(self._on_manual_fill)

    # ----- public API -----
    def set_strategy(self, strategy: Strategy) -> None:
        with self._lock:
            if self.loop and self.loop.is_running:
                raise RuntimeError("Stop the engine before swapping strategies.")
            self.strategy = strategy
            self.loop = TradingEventLoop(
                feed=self.feed,
                strategy=strategy,
                execution=self.execution,
                portfolio=self.portfolio,
                risk=self.risk,
                respect_market_hours=self.config.respect_market_hours,
            )

    def start(self) -> None:
        """Start strategy execution. Requires `set_strategy()` first."""
        if self.strategy is None or self.loop is None:
            raise RuntimeError("Call set_strategy() first")
        # If we were running engine-only, stop the feed before the loop starts
        # it again with the strategy's symbol set.
        if self._engine_only_running:
            try:
                self.feed.stop()
            except Exception:  # pragma: no cover - defensive
                self.logger.exception("feed.stop() during start() raised")
            self._engine_only_running = False
        self.loop.start()

    def stop(self) -> None:
        if self.loop is not None and self.loop.is_running:
            self.loop.stop()
        if self._engine_only_running:
            try:
                self.feed.stop()
            except Exception:  # pragma: no cover - defensive
                self.logger.exception("feed.stop() raised")
            self._engine_only_running = False

    @property
    def is_running(self) -> bool:
        return self.loop is not None and self.loop.is_running

    @property
    def is_engine_running(self) -> bool:
        """True when the data feed is running (strategy may or may not be active)."""
        return self.is_running or self._engine_only_running

    # ----- engine-only / manual-trading mode -----
    def start_engine_only(self, symbols: list[str] | None = None) -> None:
        """Start the data feed and execution layer without a strategy.

        Lets the UI fetch live prices and place manual orders without committing
        to a strategy. Strategies can still be added later via `set_strategy()`
        followed by `start()`.
        """
        with self._lock:
            if self.is_running:
                return
            if symbols:
                for s in symbols:
                    self._symbols.add(s)
            if self._symbols:
                self.feed.subscribe(sorted(self._symbols))
            self.feed.start()
            self._engine_only_running = True
            self.logger.info(
                "Engine-only mode started with symbols=%s", sorted(self._symbols),
            )

    def add_symbol(self, symbol: str) -> None:
        sym = symbol.strip().upper()
        if not sym:
            return
        with self._lock:
            if sym in self._symbols:
                return
            self._symbols.add(sym)
            self.feed.subscribe([sym])

    def remove_symbol(self, symbol: str) -> None:
        sym = symbol.strip().upper()
        with self._lock:
            self._symbols.discard(sym)
            self.feed.unsubscribe([sym])

    def watchlist(self) -> list[str]:
        with self._lock:
            return sorted(self._symbols)

    def last_prices(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for sym in self.watchlist():
            price = self.feed.get_last_price(sym)
            if price is not None:
                out[sym] = float(price)
        return out

    def place_manual_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
    ) -> Order:
        """Submit a manual paper trade via the execution engine.

        Auto-subscribes the symbol if it is not already in the watchlist and
        starts the feed if needed. Raises ValueError on invalid input.
        """
        sym = (symbol or "").strip().upper()
        if not sym:
            raise ValueError("Symbol is required")
        try:
            quantity = int(quantity)
        except (TypeError, ValueError) as exc:
            raise ValueError("Quantity must be an integer") from exc
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if order_type is OrderType.LIMIT and (limit_price is None or float(limit_price) <= 0):
            raise ValueError("Limit orders require a positive limit_price")

        if sym not in self._symbols:
            self.add_symbol(sym)
        if not self.is_engine_running:
            self.start_engine_only(symbols=[sym])
            # Wait briefly for the feed to surface a first price.
            for _ in range(20):
                if self.feed.get_last_price(sym) is not None:
                    break
                time.sleep(0.05)

        order = Order(
            symbol=sym,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=float(limit_price) if limit_price is not None else None,
            strategy="MANUAL",
            metadata={"reason": "manual"},
        )
        self.execution.submit(order)
        return order

    # ----- analytics -----
    def trades(self) -> list[Trade]:
        with self._lock:
            return list(self._trade_log)

    def trades_df(self):
        return trades_dataframe(self.trades())

    def equity_df(self):
        rows = self.storage.equity_curve(self.session_id)
        return equity_dataframe(rows)

    def performance(self) -> PerformanceReport:
        rows = self.storage.equity_curve(self.session_id)
        return compute_performance(self.portfolio, self.trades(), rows)

    def snapshot(self) -> dict:
        snap = self.portfolio.snapshot()
        snap["session_id"] = self.session_id
        snap["is_running"] = self.is_running
        snap["risk_halted"] = self.risk.is_halted() if self.risk else False
        return snap

    def market_status(self) -> dict:
        from utils.market_hours import is_market_open

        return {
            "open": bool(is_market_open()),
            "now_ist": now_ist().strftime("%a %d-%b %H:%M:%S"),
        }

    def ohlc(self, symbol: str, freq: str = "15s", lookback: int = 200) -> pd.DataFrame:
        """Resample captured ticks into an OHLC dataframe for charting.

        `freq` is any pandas resample frequency; `lookback` caps the number of
        bars returned (the most recent ones).
        """
        with self._lock:
            ticks = list(self._tick_history.get(symbol.upper(), []))
        if not ticks:
            return pd.DataFrame(columns=["open", "high", "low", "close"])
        df = pd.DataFrame(
            {"price": [t.ltp for t in ticks]},
            index=pd.DatetimeIndex([t.timestamp for t in ticks], name="timestamp"),
        )
        ohlc = df["price"].resample(freq).ohlc().dropna()
        if lookback and len(ohlc) > lookback:
            ohlc = ohlc.iloc[-lookback:]
        return ohlc

    # ----- internals -----
    def _capture_trade(self, trade: Trade) -> None:
        with self._lock:
            self._trade_log.append(trade)

    def _capture_tick(self, tick: Tick) -> None:
        with self._lock:
            buf = self._tick_history.get(tick.symbol)
            if buf is None:
                buf = deque(maxlen=self._tick_history_max)
                self._tick_history[tick.symbol] = buf
            buf.append(tick)

    def _on_manual_fill(self, trade: Trade, order: Order) -> None:
        """Apply trade to portfolio when the trading event loop is not active.

        When `set_strategy()` has been called and `loop.start()` ran, the loop
        also wires `execution.on_trade → portfolio.apply_trade`, so we skip
        here to avoid double-applying.
        """
        if self.loop is not None and self.loop.is_running:
            return
        if order.status is not OrderStatus.FILLED:
            return
        self.portfolio.apply_trade(trade)
