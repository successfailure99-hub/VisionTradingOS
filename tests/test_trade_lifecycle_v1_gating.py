from dataclasses import replace

from application.trade_lifecycle_v1 import TradeLifecycleBlockSource, TradeLifecycleOutcome, TradeLifecycleStage
from engines.market_context_v2.enums import MarketContextReadiness, MarketDirection, TradePosture
from tests.test_risk_management_v2_calculator import account
from tests.test_trade_lifecycle_v1_coordinator import coordinator
from tests.test_trade_lifecycle_v1_models import request


def test_strategy_insufficient_stops_before_risk():
    req = request()
    context = replace(
        req.market_context,
        direction=MarketDirection.INSUFFICIENT_DATA,
        readiness=MarketContextReadiness.INSUFFICIENT,
        trade_posture=TradePosture.INSUFFICIENT_DATA,
        confidence=0.0,
        primary_sources_available=0,
        bullish_score=0,
        bearish_score=0,
        net_score=0,
    )
    item = coordinator()
    item.start()
    snapshot = item.process(replace(req, market_context=context))

    assert snapshot.stage is TradeLifecycleStage.INSUFFICIENT_DATA
    assert snapshot.outcome is TradeLifecycleOutcome.INSUFFICIENT_DATA
    assert snapshot.block_source is TradeLifecycleBlockSource.DATA
    assert snapshot.risk_decision is None


def test_risk_rejection_stops_before_execution():
    req = request()
    item = coordinator()
    item.start()
    snapshot = item.process(replace(req, account_risk_state=account(realized_pnl_today=-300.0)))

    assert snapshot.stage is TradeLifecycleStage.REJECTED
    assert snapshot.outcome is TradeLifecycleOutcome.REJECTED
    assert snapshot.block_source is TradeLifecycleBlockSource.RISK
    assert snapshot.execution_result is None
