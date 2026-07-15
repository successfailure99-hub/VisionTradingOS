from datetime import timedelta

from core.enums.instrument import Instrument
from engines.production_safety_v1 import ManualSafetyCommand, ProductionSafetyStatus, ProductionSafetyV1Engine, SafetyDecision, SafetyScope
from tests.test_market_context_v2_integration import NOW
from tests.test_production_safety_v1_integration import safety_input


def started_engine():
    engine = ProductionSafetyV1Engine()
    engine.start()
    return engine


def test_monitoring_to_degraded_to_locked_transitions():
    engine = started_engine()

    assert engine.evaluate(safety_input()).status is ProductionSafetyStatus.MONITORING
    degraded = engine.evaluate(safety_input(market_data_age=timedelta(seconds=20)))
    assert degraded.status is ProductionSafetyStatus.DEGRADED
    locked = engine.evaluate(safety_input(realized=-250.0))
    assert locked.status is ProductionSafetyStatus.LOCKED
    assert locked.decision is SafetyDecision.BLOCK_GLOBAL


def test_instrument_manual_lock_transition_is_isolated():
    engine = started_engine()

    healthy = engine.evaluate(safety_input())
    assert healthy.decision is SafetyDecision.ALLOW

    manual = engine.activate_instrument_kill_switch(
        ManualSafetyCommand(
            healthy.timestamp + timedelta(minutes=1),
            SafetyScope.INSTRUMENT,
            Instrument.NIFTY,
            "transition test",
        )
    )

    assert manual.status is ProductionSafetyStatus.DEGRADED
    assert manual.decision is SafetyDecision.BLOCK_INSTRUMENT
    assert manual.global_locked is False
    nifty = next(item for item in manual.instruments if item.instrument is Instrument.NIFTY)
    assert nifty.locked is True
    assert nifty.decision is SafetyDecision.BLOCK_INSTRUMENT


def test_global_lock_recovery_transition():
    engine = started_engine()

    locked = engine.evaluate(safety_input(realized=-250.0))
    assert locked.status is ProductionSafetyStatus.LOCKED
    assert locked.decision is SafetyDecision.BLOCK_GLOBAL

    pending = engine.request_recovery(safety_input())
    assert pending.status is ProductionSafetyStatus.RECOVERY_PENDING


def test_existing_global_lock_takes_precedence_over_instrument_lock():
    engine = started_engine()

    global_locked = engine.evaluate(safety_input(realized=-250.0))
    assert global_locked.decision is SafetyDecision.BLOCK_GLOBAL

    result = engine.activate_instrument_kill_switch(
        ManualSafetyCommand(
            global_locked.timestamp + timedelta(minutes=1),
            SafetyScope.INSTRUMENT,
            Instrument.NIFTY,
            "instrument lock while globally locked",
        )
    )

    assert result.decision is SafetyDecision.BLOCK_GLOBAL
    assert result.global_locked is True
    assert result.status is ProductionSafetyStatus.LOCKED
    nifty = next(item for item in result.instruments if item.instrument is Instrument.NIFTY)
    assert nifty.locked is True
