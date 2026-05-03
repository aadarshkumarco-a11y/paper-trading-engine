"""High-level wiring used by the CLI and Streamlit UI."""
from __future__ import annotations

import threading
from dataclasses import dataclass

from analytics.metrics import (
    PerformanceReport,
    compute_performance,
    equity_dataframe,
    trades_dataframe,
)
from data_feed.base import DataFeed
from data_feed.factory import create_feed
from execution_engine.brokerage import BrokerageModel, ZerodhaEquityBrokerage
from execution_engine.engine import ExecutionEngine
from execution_engine.event_loop import TradingEventLoop
from execution_engine.orders import Trade
from portfolio.book import Portfolio
from portfolio.risk import RiskConfig, RiskManager
from portfolio.storage import PortfolioStorage
from strategy_engine.base import Strategy
from utils.config import get_settings
from utils.logger import get_logger


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
        self.portfolio.on_trade(self._capture_trade)

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
        if self.strategy is None or self.loop is None:
            raise RuntimeError("Call set_strategy() first")
        self.loop.start()

    def stop(self) -> None:
        if self.loop is not None:
            self.loop.stop()

    @property
    def is_running(self) -> bool:
        return self.loop is not None and self.loop.is_running

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

    # ----- internals -----
    def _capture_trade(self, trade: Trade) -> None:
        with self._lock:
            self._trade_log.append(trade)
