"""Paper execution simulator."""
from __future__ import annotations

import datetime as dt
import random
import json
from typing import Dict, Any, Optional

from .settled_cash_ledger import SettledCashLedger
from . import storage


def place_bracket_order(
    db_path: str,
    order_intent: Dict[str, Any],
    qty: int,
    candidate_ref: str,
    strategy_id: str,
    ledger: SettledCashLedger,
    rng: Optional[random.Random] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    now = dt.datetime.utcnow()
    entry_price = order_intent["entry"]["price"]
    stop_price = order_intent["stop"]["price"]
    take_profit_price = order_intent["take_profit"]["price"]

    cost = entry_price * qty
    ledger.on_buy_fill(cost)

    trade = {
        "symbol": candidate_ref.split(":")[1] if ":" in candidate_ref else "",
        "side": "BUY",
        "qty": qty,
        "entry_price": entry_price,
        "exit_price": None,
        "pnl": None,
        "opened_at": now.isoformat(),
        "closed_at": None,
        "strategy_id": strategy_id,
        "candidate_ref": candidate_ref,
        "status": "OPEN",
    }
    trade_id = storage.insert_trade(db_path, trade)
    storage.insert_fill(
        db_path,
        {"trade_id": trade_id, "side": "BUY", "price": entry_price, "qty": qty, "timestamp": now.isoformat()},
    )

    if rng is None:
        rng = random.Random(hash(candidate_ref))
    win = rng.random() >= 0.5
    exit_price = take_profit_price if win else stop_price
    exit_time = now + dt.timedelta(minutes=1)
    pnl = (exit_price - entry_price) * qty
    ledger.on_sell_fill(exit_price * qty, exit_time.date())

    storage.insert_fill(
        db_path,
        {"trade_id": trade_id, "side": "SELL", "price": exit_price, "qty": qty, "timestamp": exit_time.isoformat()},
    )

    if verbose:
        print(
            json.dumps(
                {
                    "candidate_ref": candidate_ref,
                    "win": win,
                    "entry": entry_price,
                    "exit": exit_price,
                    "qty": qty,
                    "pnl": pnl,
                },
                indent=2,
            )
        )

    closed_trade = trade | {
        "exit_price": exit_price,
        "pnl": pnl,
        "closed_at": exit_time.isoformat(),
        "status": "CLOSED",
        "id": trade_id,
    }
    storage.update_trade(
        db_path,
        trade_id,
        {
            "exit_price": exit_price,
            "pnl": pnl,
            "closed_at": exit_time.isoformat(),
            "status": "CLOSED",
        },
    )

    return closed_trade
