"""Metrics helpers."""
from __future__ import annotations

from typing import Optional


def r_multiple(pnl: float, risk_per_trade: float) -> float:
    if risk_per_trade == 0:
        return 0.0
    return pnl / risk_per_trade


def daily_summary(pnl: float, trades: int, avg_r: Optional[float] = None) -> dict:
    return {
        "pnl": pnl,
        "trades": trades,
        "r_multiple": avg_r if avg_r is not None else 0.0,
    }
