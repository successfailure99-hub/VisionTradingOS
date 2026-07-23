from application.trade_lifecycle_v1 import TradeLifecycleBlockSource, TradeLifecycleOutcome, TradeLifecycleStage
from tests.test_risk_management_v2_calculator import account, calculate, risk_input, strategy
from tests.test_trade_lifecycle_v1_coordinator import coordinator
from tests.test_trade_lifecycle_v1_models import request


def test_strategy_insufficient_stops_before_risk():
    risk = calculate(risk_input(strategy("insufficient")))
    req = request(risk)
    item = coordinator()
    item.start()
    snapshot = item.process(req)

    assert snapshot.stage is TradeLifecycleStage.INSUFFICIENT_DATA
    assert snapshot.outcome is TradeLifecycleOutcome.INSUFFICIENT_DATA
    assert snapshot.block_source is TradeLifecycleBlockSource.DATA
    assert snapshot.risk_decision is risk


def test_risk_rejection_stops_before_execution():
    risk = calculate(risk_input(account=account(realized_pnl_today=-300.0)))
    req = request(risk)
    item = coordinator()
    item.start()
    snapshot = item.process(req)

    assert snapshot.stage is TradeLifecycleStage.REJECTED
    assert snapshot.outcome is TradeLifecycleOutcome.REJECTED
    assert snapshot.block_source is TradeLifecycleBlockSource.RISK
    assert snapshot.execution_result is None
