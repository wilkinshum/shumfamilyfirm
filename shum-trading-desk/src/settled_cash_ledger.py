"""Cash ledger for T+1 settlement (simplified, ignores holidays)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class SettledCashLedger:
    settled_cash: float
    unsettled_proceeds: List[Dict[str, float]] = field(default_factory=list)

    def on_buy_fill(self, cost: float) -> None:
        self.settled_cash -= cost

    def on_sell_fill(self, proceeds: float, trade_date: dt.date) -> None:
        settle_date = next_business_day(trade_date)
        self.unsettled_proceeds.append({"amount": proceeds, "settle_date": settle_date.toordinal()})

    def roll_settlements(self, current_date: dt.date) -> None:
        matured = [p for p in self.unsettled_proceeds if p["settle_date"] <= current_date.toordinal()]
        remaining = [p for p in self.unsettled_proceeds if p["settle_date"] > current_date.toordinal()]
        for p in matured:
            self.settled_cash += p["amount"]
        self.unsettled_proceeds = remaining


def next_business_day(d: dt.date) -> dt.date:
    """Return next business day; ignores market holidays."""
    weekday = d.weekday()
    if weekday >= 4:  # Friday or weekend
        offset = 7 - weekday
    else:
        offset = 1
    return d + dt.timedelta(days=offset)
