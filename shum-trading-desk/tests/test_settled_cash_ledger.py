import datetime as dt

from src.settled_cash_ledger import SettledCashLedger, next_business_day


def test_buy_reduces_settled():
    ledger = SettledCashLedger(settled_cash=1000.0)
    ledger.on_buy_fill(200.0)
    assert ledger.settled_cash == 800.0


def test_sell_creates_unsettled_and_rolls():
    trade_date = dt.date(2024, 1, 5)  # Friday
    ledger = SettledCashLedger(settled_cash=1000.0)
    ledger.on_sell_fill(300.0, trade_date)
    assert ledger.settled_cash == 1000.0
    assert len(ledger.unsettled_proceeds) == 1
    settle_date = next_business_day(trade_date)
    ledger.roll_settlements(settle_date)
    assert ledger.settled_cash == 1300.0
    assert ledger.unsettled_proceeds == []
