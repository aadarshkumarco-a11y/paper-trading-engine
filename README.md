# NSE Paper Trading Engine

A production-grade **paper-trading** application for Indian markets (NSE stocks
and options). It pulls live market data, runs user-defined strategies on every
tick, simulates order execution with slippage and brokerage, persists every
fill in SQLite and surfaces the result through a Streamlit dashboard.

> **Paper trading only — no real money is ever sent to a broker.**

## Features

- **Live data feeds**
  - `yfinance` polling (works without any credentials, default)
  - Public NSE option-chain fetcher (NIFTY / BANKNIFTY / FINNIFTY / equities)
  - Pluggable adapters for Zerodha **Kite Connect** and Angel One **SmartAPI**
- **Strategy engine** with a clean `Strategy` base class
  - Built-ins: **RSI**, **EMA crossover**, **Donchian breakout**
  - Custom strategies via `path/to/file.py:ClassName`
- **Execution engine** simulating MARKET / LIMIT orders, slippage,
  per-leg brokerage (Zerodha-like by default) and execution latency
- **Portfolio book** with realized + unrealized PnL, multi-symbol positions
  and SQLite persistence
- **Risk manager** enforcing stop-loss, take-profit, max % capital per trade
  and max daily loss
- **Analytics**: equity curve, ROI, win-rate, profit factor, max drawdown
- **Options support**: ATM strike picker, weekly expiry helpers, CE/PE
  selection
- **Streamlit UI** with live PnL, trade log, equity chart, and start/stop
  controls
- Headless **CLI** entrypoint (`python main.py …`)
- CI: lint (ruff) + tests (pytest) on Python 3.11 & 3.12

## Project layout

```
paper-trading-engine/
├── data_feed/        # DataFeed base + yfinance / NSE / Kite / Angel adapters
├── strategy_engine/  # Strategy base + indicators + RSI / EMA / Breakout / options
├── execution_engine/ # Orders, brokerage, paper executor, event loop
├── portfolio/        # Position book, SQLite storage, risk manager
├── analytics/        # PnL, ROI, drawdown, win-rate, profit-factor
├── ui/               # Streamlit dashboard
├── utils/            # config, logging, market-hours
├── examples/         # Example custom strategies
├── tests/            # pytest suite
├── engine.py         # High-level wiring used by CLI + UI
├── main.py           # CLI entrypoint
└── requirements*.txt
```

## Quick start

```bash
git clone <this-repo>
cd paper-trading-engine
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # optional - only needed for Kite/Angel
```

### Streamlit dashboard

```bash
streamlit run ui/streamlit_app.py
```

Configure the strategy, symbols and capital in the sidebar, then press
**Start trading**. The app polls live yfinance quotes by default — strategies
will run on every tick and trades will appear in the trade log within seconds.

### Headless run

```bash
python main.py --strategy RSI --symbols INFY TCS --capital 200000 \
               --max-pct-per-trade 0.20 --stop-loss-pct 0.02 --take-profit-pct 0.04
```

Use `--custom path/to/file.py:ClassName` to load a custom strategy:

```bash
python main.py --custom examples/custom_strategy.py:MeanReversion --symbols RELIANCE
```

## Writing a custom strategy

Subclass `Strategy` and implement `on_tick`:

```python
from data_feed.base import Tick
from strategy_engine.base import Signal, SignalType, Strategy
from strategy_engine.indicators import rsi


class MyRSIStrategy(Strategy):
    def __init__(self, symbols, quantity=1):
        super().__init__(symbols, quantity=quantity)

    def on_tick(self, tick: Tick) -> Signal | None:
        self.context.update(tick)
        closes = self.context.closes(tick.symbol)
        if len(closes) < 15:
            return None
        if rsi(closes, 14).iloc[-1] < 25:
            return Signal(SignalType.BUY, tick.symbol, self.quantity, tick.ltp, "RSI<25")
        return None
```

`self.context.update(tick)` keeps a rolling buffer of closes/highs/lows per
symbol, available as pandas Series via `closes(symbol)`, `highs(symbol)` and
`lows(symbol)`.

## Connecting a real broker feed

The engine works fully without broker credentials thanks to the yfinance
fallback. To upgrade to a true WebSocket feed:

1. Install the broker SDK:
   ```bash
   pip install kiteconnect          # Zerodha
   # or
   pip install smartapi-python pyotp  # Angel One
   ```
2. Set the credentials in `.env` (see `.env.example`).
3. Switch the feed:
   ```bash
   PAPER_TRADING_DATA_FEED=kite python main.py --strategy RSI --symbols INFY
   # or pass --feed kite on the CLI / select it in the UI
   ```

The `KiteDataFeed` wires `KiteTicker` ticks into the engine's `Tick` model;
`AngelDataFeed` is a stub showing the same hook points.

## Risk management

| Knob                         | Default | Notes                                                      |
| ---------------------------- | ------- | ---------------------------------------------------------- |
| `max_capital_pct_per_trade`  | `0.20`  | Max fraction of equity that can be deployed in one trade   |
| `stop_loss_pct`              | `0.02`  | Adverse move that fires an EXIT on every tick              |
| `take_profit_pct`            | `0.04`  | Favorable move that fires an EXIT on every tick            |
| `max_daily_loss`             | `None`  | Halts new orders for the rest of the day once breached     |
| `allow_short`                | `False` | Block naked shorts unless explicitly enabled               |

## Options trading

```python
from data_feed import NSEOptionChain
from strategy_engine.options import select_atm_option

oc = NSEOptionChain()
atm_call = select_atm_option(oc, underlying="NIFTY", option_type="CE")
print(atm_call.strike, atm_call.expiry, atm_call.contract.ltp)
```

`select_atm_option` picks the next weekly expiry by default and supports
strike offsets (`offset=+1` for one strike OTM, etc.).

## Database

All trades and equity-curve points are persisted to SQLite at
`runtime/paper_trading.db` (override with `PAPER_TRADING_DB`). Schema:
`sessions`, `trades`, `equity_curve`. Use `PortfolioStorage.replay_trades` to
reconstruct any historical session.

## Edge cases handled

- **API failure / no live price**: market orders are rejected with a clear
  reason; the loop continues.
- **Market closed**: enable `--respect-market-hours` to pause the strategy
  outside 09:15–15:30 IST on weekdays.
- **Invalid symbol**: yfinance returns no data, no tick is published, no
  signal fires.
- **Threaded fills**: every public surface (`Portfolio`, `RiskManager`,
  `ExecutionEngine`) is guarded by a re-entrant lock.

## Development

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

CI runs both on every PR. See `.github/workflows/ci.yml`.

## Disclaimer

This project simulates trading. No part of it places real orders. It is
provided **for educational and research purposes only** and is not financial
advice. Use at your own risk.
