"""SQLite storage helpers."""
from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Any, Dict, Tuple

DB_FILENAME = "shum_trading.db"


def init_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            side TEXT,
            qty INTEGER,
            entry_price REAL,
            exit_price REAL,
            pnl REAL,
            opened_at TEXT,
            closed_at TEXT,
            strategy_id TEXT,
            candidate_ref TEXT,
            status TEXT
        );

        CREATE TABLE IF NOT EXISTS fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER,
            side TEXT,
            price REAL,
            qty INTEGER,
            timestamp TEXT,
            FOREIGN KEY(trade_id) REFERENCES trades(id)
        );

        CREATE TABLE IF NOT EXISTS daily_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            pnl REAL,
            trades INTEGER,
            r_multiple REAL
        );

        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            severity TEXT,
            message TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def insert_trade(db_path: str, trade: Dict[str, Any]) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO trades(symbol, side, qty, entry_price, exit_price, pnl, opened_at, closed_at, strategy_id, candidate_ref, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trade["symbol"],
            trade["side"],
            trade["qty"],
            trade.get("entry_price"),
            trade.get("exit_price"),
            trade.get("pnl"),
            trade.get("opened_at"),
            trade.get("closed_at"),
            trade.get("strategy_id"),
            trade.get("candidate_ref"),
            trade.get("status", "CLOSED"),
        ),
    )
    trade_id = cur.lastrowid
    conn.commit()
    conn.close()
    return trade_id


def update_trade(db_path: str, trade_id: int, updates: Dict[str, Any]) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE trades
        SET exit_price = ?, pnl = ?, closed_at = ?, status = ?
        WHERE id = ?
        """,
        (
            updates.get("exit_price"),
            updates.get("pnl"),
            updates.get("closed_at"),
            updates.get("status", "CLOSED"),
            trade_id,
        ),
    )
    conn.commit()
    conn.close()


def insert_fill(db_path: str, fill: Dict[str, Any]) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO fills(trade_id, side, price, qty, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            fill["trade_id"],
            fill["side"],
            fill["price"],
            fill["qty"],
            fill["timestamp"],
        ),
    )
    conn.commit()
    conn.close()


def insert_metric(db_path: str, metric: Dict[str, Any]) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO daily_metrics(date, pnl, trades, r_multiple)
        VALUES (?, ?, ?, ?)
        """,
        (metric["date"], metric.get("pnl", 0.0), metric.get("trades", 0), metric.get("r_multiple", 0.0)),
    )
    conn.commit()
    conn.close()


def insert_incident(db_path: str, incident: Dict[str, Any]) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO incidents(created_at, severity, message)
        VALUES (?, ?, ?)
        """,
        (
            incident.get("created_at", dt.datetime.utcnow().isoformat()),
            incident.get("severity", "INFO"),
            incident.get("message", ""),
        ),
    )
    conn.commit()
    conn.close()


def fetch_today_state(db_path: str, today: dt.date) -> Tuple[float, float, int]:
    """Return equity estimate, daily pnl, consecutive losses; defaults to flat if empty."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT SUM(pnl) FROM trades")
    total_pnl = cur.fetchone()[0] or 0.0
    cur.execute("SELECT SUM(pnl) FROM trades WHERE date(closed_at)=?", (today.isoformat(),))
    daily_pnl = cur.fetchone()[0] or 0.0
    cur.execute(
        """
        SELECT pnl FROM trades ORDER BY closed_at DESC LIMIT 5
        """
    )
    rows = cur.fetchall()
    consecutive_losses = 0
    for r in rows:
        if r[0] is not None and r[0] < 0:
            consecutive_losses += 1
        else:
            break
    conn.close()
    equity = 100_000 + total_pnl
    return equity, daily_pnl, consecutive_losses
