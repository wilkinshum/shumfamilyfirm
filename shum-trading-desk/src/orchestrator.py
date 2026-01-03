"""Main orchestrator entrypoint for paper-only desk."""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Dict, Any, List

from .utils import load_yaml
from .llm_client import MockLLMClient
from .risk_engine import RiskConfig, approve_or_reject
from .settled_cash_ledger import SettledCashLedger
from .execution_paper import place_bracket_order
from .market_data import MarketDataClient
from . import storage
from . import metrics

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DB_PATH = os.path.join(BASE_DIR, "shum_trading.db")


def run() -> None:
    risk_cfg = RiskConfig.from_dict(load_yaml(os.path.join(CONFIG_DIR, "risk.yaml")))
    universe_cfg = load_yaml(os.path.join(CONFIG_DIR, "universe.yaml"))
    universe = universe_cfg.get("symbols", [])

    storage.init_db(DB_PATH)
    equity, daily_pnl, consecutive_losses = storage.fetch_today_state(DB_PATH, dt.date.today())
    ledger = SettledCashLedger(settled_cash=equity)

    llm = MockLLMClient(universe=universe)
    cio_plan = llm.complete("cio", {}).content
    market_data_resp = llm.complete("market_data", {}).content
    news_resp = llm.complete("news_risk", {}).content
    if not market_data_resp.get("ok", True):
        print("Halting: market data quality issue")
        return
    if news_resp.get("blocked"):
        print("Halting: news risk blocked symbols")
        return

    strategy_outputs = {}
    for call in cio_plan.get("agent_calls", []):
        agent = call.get("agent")
        if agent.startswith("strategy_"):
            out = llm.complete(agent, call.get("input", {})).content
            strategy_outputs[agent] = out

    candidates: Dict[str, Dict[str, Any]] = {}
    for agent, payload in strategy_outputs.items():
        if not payload.get("data_quality", {}).get("ok", False):
            print(f"Halting: data quality failed for {agent}")
            return
        strategy_id = payload.get("strategy_id", agent.replace("strategy_", ""))
        for c in payload.get("candidates", []):
            ref = f"{strategy_id}:{c['symbol']}:{payload.get('as_of')}"
            candidates[ref] = c | {"candidate_ref": ref, "strategy_id": strategy_id}

    market_client = MarketDataClient(market_data_resp.get("snapshots", []))
    snapshots = market_client.fetch(universe)

    executed: List[Dict[str, Any]] = []
    trade_count = 0
    for intent in sorted(cio_plan.get("trade_intents", []), key=lambda x: x.get("priority", 0)):
        if trade_count >= risk_cfg.max_trades_per_day:
            break
        ref = intent.get("candidate_ref")
        candidate = candidates.get(ref)
        if not candidate:
            continue
        snap = snapshots.get(candidate["symbol"], {})
        approval = approve_or_reject(
            candidate,
            risk_cfg,
            equity=equity,
            settled_cash_available=ledger.settled_cash,
            daily_loss_to_date=daily_pnl,
            weekly_loss_to_date=0.0,
            consecutive_losses=consecutive_losses,
            market_snapshot=snap,
        )
        print(json.dumps(approval, indent=2))
        if approval["decision"] != "APPROVE":
            continue
        trade = place_bracket_order(
            db_path=DB_PATH,
            order_intent=approval["order_intent"],
            qty=approval["qty"],
            candidate_ref=ref,
            strategy_id=candidate.get("strategy_id", ""),
            ledger=ledger,
        )
        executed.append(trade)
        trade_count += 1
        equity += trade.get("pnl", 0.0)
        daily_pnl += trade.get("pnl", 0.0)
        consecutive_losses = 0 if trade.get("pnl", 0.0) >= 0 else consecutive_losses + 1
        ledger.roll_settlements(dt.date.today())

    summary = metrics.daily_summary(pnl=daily_pnl, trades=len(executed))
    storage.insert_metric(DB_PATH, {"date": dt.date.today().isoformat(), **summary})

    print("Daily summary")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run()
