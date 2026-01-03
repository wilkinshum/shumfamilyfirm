"""Mock LLM client for deterministic agent outputs."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, List

ISOFORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class LLMResponse:
    agent: str
    content: Dict[str, Any]


class MockLLMClient:
    """Deterministic mock that returns schema-conformant JSON for agents."""

    def __init__(self, universe: List[str] | None = None) -> None:
        self.universe = universe or ["SPY", "QQQ"]
        self.as_of = dt.datetime.utcnow().strftime(ISOFORMAT)

    def complete(self, agent: str, payload: Dict[str, Any] | None = None) -> LLMResponse:
        agent_lower = agent.lower()
        if agent_lower == "cio":
            return LLMResponse(agent="cio", content=self._cio_plan())
        if agent_lower == "market_data":
            return LLMResponse(agent="market_data", content=self._market_data())
        if agent_lower == "news_risk":
            return LLMResponse(agent="news_risk", content=self._news())
        if agent_lower in {"strategy_orb", "strategy_vwap"}:
            strategy_id = agent_lower.replace("strategy_", "")
            return LLMResponse(agent=agent_lower, content=self._strategy_signal(strategy_id))
        # Developer agent stub
        return LLMResponse(agent=agent_lower, content={"notes": "No-op"})

    def _cio_plan(self) -> Dict[str, Any]:
        today = dt.date.today()
        return {
            "session_plan": {
                "mode": "PAPER",
                "date": today.isoformat(),
                "universe": self.universe,
                "strategies_enabled": ["orb", "vwap"],
                "max_trades_today": 3,
            },
            "agent_calls": [
                {"agent": "market_data", "input": {"universe": self.universe}},
                {"agent": "news_risk", "input": {"universe": self.universe}},
                {"agent": "strategy_orb", "input": {"universe": self.universe}},
                {"agent": "strategy_vwap", "input": {"universe": self.universe}},
            ],
            "trade_intents": [
                {"candidate_ref": f"orb:{sym}:{self.as_of}" , "priority": 1}
                for sym in self.universe
            ]
            + [
                {"candidate_ref": f"vwap:{sym}:{self.as_of}" , "priority": 2}
                for sym in self.universe
            ],
            "notes": "Deterministic mock CIO plan",
        }

    def _market_data(self) -> Dict[str, Any]:
        return {
            "as_of": dt.datetime.utcnow().strftime(ISOFORMAT),
            "ok": True,
            "issues": [],
            "snapshots": [
                {
                    "symbol": sym,
                    "last": 100.0,
                    "bid": 99.9,
                    "ask": 100.1,
                    "spread": 0.002,
                    "avg_volume": 6_000_000,
                }
                for sym in self.universe
            ],
        }

    def _news(self) -> Dict[str, Any]:
        return {
            "as_of": dt.datetime.utcnow().strftime(ISOFORMAT),
            "blocked": [],
            "notes": "No adverse news detected",
        }

    def _strategy_signal(self, strategy_id: str) -> Dict[str, Any]:
        as_of = self.as_of
        # Deterministic pricing to satisfy RR>=3
        entry = 100.0
        stop = 98.5
        take_profit = 105.0
        return {
            "as_of": as_of,
            "strategy_id": strategy_id,
            "universe": self.universe,
            "candidates": [
                {
                    "symbol": sym,
                    "side": "BUY",
                    "entry": {"type": "LIMIT", "price": entry},
                    "stop": {"type": "STOP", "price": stop},
                    "take_profit": {"type": "LIMIT", "price": take_profit},
                    "time_in_force": "DAY",
                    "setup_tags": [strategy_id, "mock"],
                    "expected_r_multiple": (take_profit - entry) / (entry - stop),
                    "confidence": 0.6,
                    "notes": "Deterministic mock candidate",
                }
                for sym in self.universe
            ],
            "data_quality": {"ok": True, "issues": []},
        }
