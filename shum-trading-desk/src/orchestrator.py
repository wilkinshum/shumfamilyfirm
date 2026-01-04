"""Main orchestrator entrypoint for paper-only desk."""
from __future__ import annotations

import datetime as dt
import json
import os
import argparse
import random
from typing import Dict, Any, List

from .utils import load_yaml, load_json_schema, validate_json
from .llm_client import MockLLMClient, OpenAIClient, LLMResponse
from .risk_engine import RiskConfig, approve_or_reject
from .settled_cash_ledger import SettledCashLedger
from .execution_paper import place_bracket_order
from .market_data import MarketDataClient
from . import storage
from . import metrics

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DB_PATH = os.path.join(BASE_DIR, "shum_trading.db")
SCHEMA_DIR = os.path.join(BASE_DIR, "schemas")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run paper orchestrator")
    parser.add_argument("--verbose", action="store_true", help="Print detailed approvals and fills")
    parser.add_argument("--seed", type=int, default=None, help="Seed for deterministic P&L outcomes")
    parser.add_argument("--llm", choices=["mock", "openai"], default="mock", help="LLM provider")
    parser.add_argument("--model", default="gpt-5.2", help="LLM model name for live mode")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Env var holding API key")
    return parser.parse_args()


def run(args: argparse.Namespace | None = None) -> None:
    args = args or parse_args()
    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    risk_cfg = RiskConfig.from_dict(load_yaml(os.path.join(CONFIG_DIR, "risk.yaml")))
    universe_cfg = load_yaml(os.path.join(CONFIG_DIR, "universe.yaml"))
    universe = universe_cfg.get("symbols", [])
    cio_schema = load_json_schema(os.path.join(SCHEMA_DIR, "cio_output.schema.json"))
    signal_schema = load_json_schema(os.path.join(SCHEMA_DIR, "signal_output.schema.json"))

    storage.init_db(DB_PATH)
    equity, daily_pnl, consecutive_losses = storage.fetch_today_state(DB_PATH, dt.date.today())
    ledger = SettledCashLedger(settled_cash=equity)

    llm = _make_llm(args, universe)
    cio_resp: LLMResponse = llm.complete("cio", {})
    validate_json(cio_resp.content, cio_schema)
    cio_plan = cio_resp.content
    market_data_resp = llm.complete("market_data", {}).content
    news_resp = llm.complete("news_risk", {}).content
    if not market_data_resp.get("ok", True):
        storage.insert_incident(DB_PATH, {"severity": "ERROR", "message": "Market data quality issue"})
        print("Halting: market data quality issue")
        return
    if news_resp.get("blocked"):
        storage.insert_incident(DB_PATH, {"severity": "ERROR", "message": "News risk blocked symbols"})
        print("Halting: news risk blocked symbols")
        return

    strategy_outputs = {}
    for call in cio_plan.get("agent_calls", []):
        agent = call.get("agent")
        if agent.startswith("strategy_"):
            out_resp = llm.complete(agent, call.get("input", {}))
            validate_json(out_resp.content, signal_schema)
            strategy_outputs[agent] = out_resp.content

    candidates: Dict[str, Dict[str, Any]] = {}
    news_by_symbol = news_resp.get("by_symbol", {})
    for agent, payload in strategy_outputs.items():
        if not payload.get("data_quality", {}).get("ok", False):
            storage.insert_incident(DB_PATH, {"severity": "ERROR", "message": f"Data quality failed for {agent}"})
            print(f"Halting: data quality failed for {agent}")
            return
        strategy_id = payload.get("strategy_id", agent.replace("strategy_", ""))
        for idx, c in enumerate(payload.get("candidates", [])):
            ref = f"{strategy_id}:{c['symbol']}:{payload.get('as_of')}:c{idx}"
            sym_news = news_by_symbol.get(c["symbol"], {"ok": True, "issues": []})
            if not sym_news.get("ok", True):
                storage.insert_incident(
                    DB_PATH,
                    {"severity": "WARN", "message": f"News blocked {c['symbol']}: {sym_news.get('issues', [])}"},
                )
                continue
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
        if args.verbose:
            print(json.dumps(approval, indent=2))
        if approval["decision"] != "APPROVE":
            storage.insert_incident(
                DB_PATH,
                {"severity": "WARN", "message": f"Rejected {ref}: {approval.get('reason')}"},
            )
            continue
        trade = place_bracket_order(
            db_path=DB_PATH,
            order_intent=approval["order_intent"],
            qty=approval["qty"],
            candidate_ref=ref,
            strategy_id=candidate.get("strategy_id", ""),
            ledger=ledger,
            rng=rng,
            verbose=args.verbose,
        )
        executed.append(trade)
        trade_count += 1
        equity += trade.get("pnl", 0.0)
        daily_pnl += trade.get("pnl", 0.0)
        consecutive_losses = 0 if trade.get("pnl", 0.0) >= 0 else consecutive_losses + 1
        ledger.roll_settlements(dt.date.today())

    summary = metrics.daily_summary(pnl=daily_pnl, trades=len(executed))
    storage.insert_metric(DB_PATH, {"date": dt.date.today().isoformat(), **summary})
    storage.insert_incident(
        DB_PATH,
        {
            "severity": "INFO",
            "message": f"Session complete trades={len(executed)} pnl={daily_pnl}",
            "created_at": dt.datetime.utcnow().isoformat(),
        },
    )

    print("Daily summary")
    print(json.dumps(summary, indent=2))


def _make_llm(args: argparse.Namespace, universe: List[str]) -> MockLLMClient | OpenAIClient:
    if args.llm == "mock":
        return MockLLMClient(universe=universe)
    api_key = os.getenv(args.api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing API key in env var {args.api_key_env}")
    prompt_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents")
    return OpenAIClient(api_key=api_key, model=args.model, prompt_dir=prompt_dir, universe=universe)


if __name__ == "__main__":
    run(parse_args())
