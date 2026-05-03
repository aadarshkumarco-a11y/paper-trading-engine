"""CLI entry point.

Usage examples:

    # Streamlit dashboard
    streamlit run ui/streamlit_app.py

    # Headless run with the RSI strategy
    python main.py --strategy RSI --symbols INFY TCS --capital 200000

    # Custom strategy from a Python file
    python main.py --custom examples/custom_strategy.py:MeanReversion --symbols RELIANCE
"""
from __future__ import annotations

import argparse
import importlib.util
import signal
import sys
import time
from pathlib import Path

from engine import EngineConfig, TradingApp
from portfolio.risk import RiskConfig
from strategy_engine.base import Strategy
from strategy_engine.registry import build_strategy, registered_strategies
from utils.logger import get_logger


def _load_custom_strategy(spec: str) -> type[Strategy]:
    """Load `path/to/file.py:ClassName`."""
    if ":" not in spec:
        raise SystemExit("Custom strategy spec must be 'path.py:ClassName'")
    path_part, class_name = spec.split(":", 1)
    path = Path(path_part).resolve()
    if not path.exists():
        raise SystemExit(f"Strategy file {path} not found")
    module_spec = importlib.util.spec_from_file_location(path.stem, path)
    if module_spec is None or module_spec.loader is None:
        raise SystemExit(f"Could not import {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    cls = getattr(module, class_name, None)
    if cls is None or not issubclass(cls, Strategy):
        raise SystemExit(f"{class_name} is not a Strategy subclass")
    return cls


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NSE paper trading engine")
    p.add_argument("--strategy", help=f"Built-in: {sorted(registered_strategies())}")
    p.add_argument("--custom", help="Custom strategy spec path/to/file.py:ClassName")
    p.add_argument("--symbols", nargs="+", required=True, help="NSE symbols (e.g. INFY TCS)")
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--quantity", type=int, default=1)
    p.add_argument("--feed", default=None, help="Override data feed (yfinance|kite|angel)")
    p.add_argument("--max-pct-per-trade", type=float, default=0.20)
    p.add_argument("--stop-loss-pct", type=float, default=0.02)
    p.add_argument("--take-profit-pct", type=float, default=0.04)
    p.add_argument("--max-daily-loss", type=float, default=None)
    p.add_argument("--respect-market-hours", action="store_true")
    p.add_argument("--run-for", type=float, default=0,
                   help="Run for N seconds and exit (0 = run until Ctrl+C)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logger = get_logger("main")

    risk = RiskConfig(
        max_capital_pct_per_trade=args.max_pct_per_trade,
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
        max_daily_loss=args.max_daily_loss,
    )
    app = TradingApp(EngineConfig(
        initial_capital=args.capital,
        feed=args.feed,
        respect_market_hours=args.respect_market_hours,
        risk=risk,
    ))

    if args.custom:
        cls = _load_custom_strategy(args.custom)
        strategy = cls(symbols=args.symbols, quantity=args.quantity)
    elif args.strategy:
        strategy = build_strategy(args.strategy, symbols=args.symbols, quantity=args.quantity)
    else:
        raise SystemExit("Specify --strategy or --custom")

    app.set_strategy(strategy)

    stop_event = {"flag": False}

    def _handle(_signum, _frame):
        logger.info("Stopping…")
        stop_event["flag"] = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    app.start()
    start_ts = time.time()
    try:
        while not stop_event["flag"]:
            time.sleep(1)
            if args.run_for and time.time() - start_ts >= args.run_for:
                break
    finally:
        app.stop()

    report = app.performance()
    logger.info("Final report: %s", report.to_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main())
