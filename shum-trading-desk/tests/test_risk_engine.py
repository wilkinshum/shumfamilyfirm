from src.risk_engine import RiskConfig, approve_or_reject


RISK_CFG = RiskConfig(
    mode="PAPER",
    risk_pct_per_trade=0.0025,
    max_daily_loss_pct=0.01,
    max_weekly_loss_pct=0.03,
    max_drawdown_pct=0.06,
    max_consecutive_losses=3,
    daily_profit_lock_pct=0.01,
    max_trades_per_day=3,
    min_rr=3.0,
    min_price=10.0,
    min_avg_volume=5_000_000,
    max_spread=0.03,
)


BASE_CANDIDATE = {
    "symbol": "SPY",
    "side": "BUY",
    "entry": {"type": "LIMIT", "price": 100.0},
    "stop": {"type": "STOP", "price": 99.0},
    "take_profit": {"type": "LIMIT", "price": 103.0},
    "time_in_force": "DAY",
}


def test_rejects_low_rr():
    cand = BASE_CANDIDATE | {"take_profit": {"type": "LIMIT", "price": 101.0}}
    decision = approve_or_reject(cand, RISK_CFG, equity=100_000, settled_cash_available=100_000)
    assert decision["decision"] == "REJECT"
    assert decision["constraints_checked"]["rr_check"] is False


def test_rejects_insufficient_cash_qty():
    decision = approve_or_reject(BASE_CANDIDATE, RISK_CFG, equity=100_000, settled_cash_available=50.0)
    assert decision["decision"] == "REJECT"
    assert decision["qty"] == 0


def test_approves_basic_case():
    decision = approve_or_reject(BASE_CANDIDATE, RISK_CFG, equity=100_000, settled_cash_available=100_000)
    assert decision["decision"] == "APPROVE"
    assert decision["qty"] > 0
    expected_qty = int((100_000 * 0.0025) // 1.0)
    assert decision["qty"] == expected_qty


def test_rejects_liquidity_constraints():
    snapshot = {"last": 9.0, "spread": 0.05, "avg_volume": 1_000_000}
    decision = approve_or_reject(
        BASE_CANDIDATE,
        RISK_CFG,
        equity=100_000,
        settled_cash_available=100_000,
        market_snapshot=snapshot,
    )
    assert decision["decision"] == "REJECT"
    assert decision["constraints_checked"]["spread_liquidity"] is False


def test_rejects_daily_loss_lockout():
    decision = approve_or_reject(
        BASE_CANDIDATE,
        RISK_CFG,
        equity=100_000,
        settled_cash_available=100_000,
        daily_loss_to_date=100_000 * RISK_CFG.max_daily_loss_pct,
    )
    assert decision["decision"] == "REJECT"
    assert decision["constraints_checked"]["max_daily_loss"] is False
