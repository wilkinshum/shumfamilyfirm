"""Market data stub for mocks."""
from __future__ import annotations

from typing import Dict, List


class MarketDataClient:
    def __init__(self, snapshots: List[Dict[str, float]] | None = None) -> None:
        self.snapshots = snapshots or []

    def fetch(self, universe: List[str]) -> Dict[str, Dict[str, float]]:
        data = {}
        for snap in self.snapshots:
            symbol = snap.get("symbol")
            if symbol in universe:
                data[symbol] = snap
        # default snapshots if missing
        for sym in universe:
            data.setdefault(sym, {"last": 100.0, "spread": 0.01, "avg_volume": 6_000_000})
        return data
