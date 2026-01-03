# Shum Family Trading Desk (Paper)

Paper-first, multi-agent orchestration where LLM agents propose JSON actions and deterministic Python enforces risk and execution. All fills are simulated and recorded in SQLite (`shum_trading.db`).

## Quickstart
1) Create venv: `python -m venv .venv && .venv\Scripts\activate`
2) Install deps: `pip install -r requirements.txt`
3) Run orchestrator (paper): `python -m src.orchestrator`

## Architecture
- Agents (CIO, strategies, market data, news) emit STRICT JSON matching schemas in `schemas/`.
- `src/orchestrator.py` drives flow: load config, call agents (mocked via `MockLLMClient`), collect candidates, enforce data quality, request deterministic risk approval, then simulate execution.
- `src/risk_engine.py` is the authority: sizes positions, enforces RR≥3, daily/weekly loss limits, cash checks, liquidity gates.
- `src/execution_paper.py` fills brackets immediately, resolves to stop/TP deterministically, updates `SettledCashLedger`, writes trades/fills to SQLite via `src/storage.py`.
- `src/settled_cash_ledger.py` models US cash account T+1 settlement (simplified: weekends only, holidays not handled in v1).
- `src/metrics.py` computes basic R-metrics; `src/market_data.py` provides stub snapshots; `src/llm_client.py` provides deterministic mock agent JSON.

## Config
- `config/risk.yaml`: risk knobs (PAPER mode, RR floor, trade limits, liquidity thresholds).
- `config/universe.yaml`: symbols universe.

## Schemas
- Strategy signals: `schemas/signal_output.schema.json`
- CIO plan: `schemas/cio_output.schema.json`
- Order intent: `schemas/order_intent.schema.json`
- Risk approval: `schemas/risk_approval.schema.json`

## Storage
SQLite file `shum_trading.db` with tables: trades, fills, daily_metrics, incidents. Initialized automatically by orchestrator.

## Tests
Run `pytest` to validate ledger settlement and risk sizing logic.

## Example run (mock, truncated)
```
{
  "decision": "APPROVE",
  "symbol": "SPY",
  "side": "BUY",
  "qty": 250,
  "reason": "Approved"
}
Daily summary
{
  "pnl": 1250.0,
  "trades": 2,
  "r_multiple": 0.0
}
```
