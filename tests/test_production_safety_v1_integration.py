from datetime import timedelta

from application.enums import ExecutionSafetyMode, RuntimeStatus
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.production_safety_v1 import ProductionSafetyV1Engine, ProductionSafetyV1Input, SafetyDecision
from engines.risk_management_v2 import AccountRiskState, SessionRiskState
from tests.test_market_context_v2_integration import NOW
from tests.test_trade_journal_runtime_integration_v1_end_to_end import integration_stack


def healthy_snapshots():
    journal_runtime, lifecycle_runtime, _journal = integration_stack()
    return lifecycle_runtime.snapshot(), journal_runtime.snapshot()


def account(realized=0.0, unrealized=0.0):
    return AccountRiskState(NOW, 10000.0, 10000.0, 10000.0, 10000.0, realized, unrealized, 0.0)


def session(trades=0, losses=0):
    return SessionRiskState(NOW.date(), trades, 0, losses, losses, 0.0)


def safety_input(realized=0.0, unrealized=0.0, trades=0, losses=0, market_data_age=timedelta(seconds=1)):
    lifecycle, journal = healthy_snapshots()
    return ProductionSafetyV1Input(
        NOW,
        RuntimeStatus.RUNNING,
        ExecutionSafetyMode.ANALYSIS_ONLY,
        BrokerExecutionMode.DRY_RUN,
        lifecycle,
        journal,
        account(realized, unrealized),
        session(trades, losses),
        tuple((instrument, NOW - market_data_age) for instrument in (Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX)),
    )


def test_no_network_production_safety_evaluates_healthy_and_breaches():
    engine = ProductionSafetyV1Engine()
    engine.start()

    healthy = engine.evaluate(safety_input())
    daily_loss = engine.evaluate(safety_input(realized=-250.0))
    trade_count = engine.evaluate(safety_input(trades=3))
    stale = engine.evaluate(safety_input(market_data_age=timedelta(seconds=35)))

    assert healthy.decision is SafetyDecision.ALLOW
    assert daily_loss.decision is SafetyDecision.BLOCK_GLOBAL
    assert trade_count.decision is SafetyDecision.BLOCK_GLOBAL
    assert stale.decision is SafetyDecision.BLOCK_INSTRUMENT
    assert stale.instruments[0].locked is True
    assert stale.instruments[1].locked is True
