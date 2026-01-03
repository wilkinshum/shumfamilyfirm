"""Deterministic risk checks for Shum Family Trading Desk."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class RiskConfig:
    mode: str
    risk_pct_per_trade: float
    max_daily_loss_pct: float
    max_weekly_loss_pct: float
    max_drawdown_pct: float
    max_consecutive_losses: int
    daily_profit_lock_pct: float
    max_trades_per_day: int
    min_rr: float
    min_price: float
    min_avg_volume: float
    max_spread: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskConfig":
        return cls(
            mode=data.get("mode", "PAPER"),
            risk_pct_per_trade=data["risk_pct_per_trade"],
            max_daily_loss_pct=data["max_daily_loss_pct"],
            max_weekly_loss_pct=data["max_weekly_loss_pct"],
            max_drawdown_pct=data["max_drawdown_pct"],
            max_consecutive_losses=data["max_consecutive_losses"],
            daily_profit_lock_pct=data["daily_profit_lock_pct"],
            max_trades_per_day=data["max_trades_per_day"],
            min_rr=data["min_rr"],
            min_price=data["min_price"],
            min_avg_volume=data["min_avg_volume"],
            max_spread=data["max_spread"],
        )


def approve_or_reject(
    candidate: Dict[str, Any],
    risk_cfg: RiskConfig,
    equity: float,
    settled_cash_available: float,
    daily_loss_to_date: float = 0.0,
    weekly_loss_to_date: float = 0.0,
    consecutive_losses: int = 0,
    market_snapshot: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    entry_price = candidate["entry"]["price"]
    stop_price = candidate["stop"]["price"]
    take_profit = candidate["take_profit"]["price"]
    stop_distance = abs(entry_price - stop_price)
    rr = (take_profit - entry_price) / stop_distance if stop_distance > 0 else 0

    constraints_checked = {
        "max_daily_loss": True,
        "max_weekly_loss": True,
        "max_consecutive_losses": True,
        "settled_cash": True,
        "spread_liquidity": True,
        "rr_check": rr >= risk_cfg.min_rr,
    }

    if candidate.get("side") != "BUY":
        return _reject(candidate, constraints_checked, reason="Only BUY allowed in v1")
    if stop_distance <= 0:
        return _reject(candidate, constraints_checked, reason="Invalid stop distance")
    if rr < risk_cfg.min_rr:
        constraints_checked["rr_check"] = False
        return _reject(candidate, constraints_checked, reason="RR below minimum")

    risk_per_trade_usd = equity * risk_cfg.risk_pct_per_trade
    qty_by_risk = math.floor(risk_per_trade_usd / stop_distance) if stop_distance > 0 else 0
    qty_by_cash = math.floor(settled_cash_available / entry_price) if entry_price > 0 else 0
    qty = min(qty_by_risk, qty_by_cash)

    expected_loss_usd = qty * stop_distance
    daily_loss_remaining = equity * risk_cfg.max_daily_loss_pct - daily_loss_to_date
    weekly_loss_remaining = equity * risk_cfg.max_weekly_loss_pct - weekly_loss_to_date

    if daily_loss_remaining <= 0:
        constraints_checked["max_daily_loss"] = False
    if weekly_loss_remaining <= 0:
        constraints_checked["max_weekly_loss"] = False
    if consecutive_losses >= risk_cfg.max_consecutive_losses:
        constraints_checked["max_consecutive_losses"] = False

    if market_snapshot:
        price = market_snapshot.get("last", entry_price)
        spread = market_snapshot.get("spread", 0)
        avg_volume = market_snapshot.get("avg_volume", risk_cfg.min_avg_volume)
        if price < risk_cfg.min_price or avg_volume < risk_cfg.min_avg_volume or spread > risk_cfg.max_spread:
            constraints_checked["spread_liquidity"] = False
    if settled_cash_available < entry_price:
        constraints_checked["settled_cash"] = False

    if qty < 1:
        return _reject(candidate, constraints_checked, reason="Insufficient size")
    if not all(constraints_checked.values()):
        return _reject(candidate, constraints_checked, reason="Constraint failure")

    order_intent = {
        "type": "BRACKET",
        "entry": candidate["entry"],
        "stop": candidate["stop"],
        "take_profit": candidate["take_profit"],
        "time_in_force": candidate.get("time_in_force", "DAY"),
    }

    return {
        "decision": "APPROVE",
        "symbol": candidate["symbol"],
        "side": "BUY",
        "qty": int(qty),
        "risk": {
            "equity": equity,
            "risk_per_trade_usd": risk_per_trade_usd,
            "stop_distance": stop_distance,
            "expected_loss_usd": expected_loss_usd,
            "daily_loss_remaining_usd": daily_loss_remaining,
            "settled_cash_remaining_usd": settled_cash_available,
        },
        "constraints_checked": constraints_checked,
        "order_intent": order_intent,
        "reason": "Approved",
    }


def _reject(candidate: Dict[str, Any], constraints: Dict[str, bool], reason: str) -> Dict[str, Any]:
    return {
        "decision": "REJECT",
        "symbol": candidate.get("symbol", ""),
        "side": candidate.get("side", "BUY"),
        "qty": 0,
        "risk": {
            "equity": 0,
            "risk_per_trade_usd": 0,
            "stop_distance": 0,
            "expected_loss_usd": 0,
            "daily_loss_remaining_usd": 0,
            "settled_cash_remaining_usd": 0,
        },
        "constraints_checked": constraints,
        "order_intent": {
            "type": "BRACKET",
            "entry": candidate.get("entry", {}),
            "stop": candidate.get("stop", {}),
            "take_profit": candidate.get("take_profit", {}),
            "time_in_force": candidate.get("time_in_force", "DAY"),
        },
        "reason": reason,
    }
