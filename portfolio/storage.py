"""SQLite persistence layer for the portfolio."""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from execution_engine.orders import OrderSide, Trade
from utils.market_hours import IST

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    initial_capital REAL NOT NULL,
    strategy TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    brokerage REAL NOT NULL,
    strategy TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS equity_curve (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    timestamp TEXT NOT NULL,
    cash REAL NOT NULL,
    positions_value REAL NOT NULL,
    equity REAL NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);
"""


class PortfolioStorage:
    """Thread-safe wrapper around a sqlite3 connection."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(SCHEMA)

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            finally:
                cur.close()

    # --- sessions ---
    def start_session(self, initial_capital: float, strategy: str = "", notes: str = "") -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions(started_at, initial_capital, strategy, notes) VALUES (?,?,?,?)",
                (datetime.now(IST).isoformat(), float(initial_capital), strategy, notes),
            )
            return int(cur.lastrowid)

    # --- trades ---
    def record_trade(self, session_id: int | None, trade: Trade) -> None:
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trades(session_id, order_id, symbol, side, quantity, price,
                                   brokerage, strategy, timestamp)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    session_id,
                    trade.order_id,
                    trade.symbol,
                    trade.side.value,
                    int(trade.quantity),
                    float(trade.price),
                    float(trade.brokerage),
                    trade.strategy,
                    trade.timestamp.isoformat(),
                ),
            )

    def trades(self, session_id: int | None = None) -> list[dict]:
        with self.cursor() as cur:
            if session_id is None:
                cur.execute("SELECT * FROM trades ORDER BY id ASC")
            else:
                cur.execute("SELECT * FROM trades WHERE session_id = ? ORDER BY id ASC", (session_id,))
            return [dict(row) for row in cur.fetchall()]

    # --- equity curve ---
    def record_equity_point(
        self,
        session_id: int | None,
        cash: float,
        positions_value: float,
        equity: float,
        ts: datetime | None = None,
    ) -> None:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO equity_curve(session_id, timestamp, cash, positions_value, equity) VALUES (?,?,?,?,?)",
                (
                    session_id,
                    (ts or datetime.now(IST)).isoformat(),
                    float(cash),
                    float(positions_value),
                    float(equity),
                ),
            )

    def equity_curve(self, session_id: int | None = None) -> list[dict]:
        with self.cursor() as cur:
            if session_id is None:
                cur.execute("SELECT * FROM equity_curve ORDER BY id ASC")
            else:
                cur.execute(
                    "SELECT * FROM equity_curve WHERE session_id = ? ORDER BY id ASC",
                    (session_id,),
                )
            return [dict(row) for row in cur.fetchall()]

    def replay_trades(self, session_id: int) -> list[Trade]:
        rows = self.trades(session_id)
        out: list[Trade] = []
        for r in rows:
            out.append(
                Trade(
                    order_id=r["order_id"],
                    symbol=r["symbol"],
                    side=OrderSide(r["side"]),
                    quantity=int(r["quantity"]),
                    price=float(r["price"]),
                    brokerage=float(r["brokerage"]),
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    strategy=r["strategy"] or "",
                )
            )
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()
