from datetime import timedelta
from threading import RLock

from engines.production_safety_v1 import (
    ManualSafetyCommand,
    ProductionSafetyStatus,
    ProductionSafetyV1Engine,
    RecoveryDecision,
    SafetyChange,
    SafetyDecision,
    SafetyIncidentStatus,
    SafetyRuleResult,
    SafetyRuleType,
    SafetyScope,
    SafetySeverity,
)
from tests.test_market_context_v2_integration import NOW
from tests.test_production_safety_v1_integration import safety_input


def test_engine_start_evaluate_manual_recovery_release_stop_and_clear():
    engine = ProductionSafetyV1Engine()

    assert engine.snapshot().status is ProductionSafetyStatus.CREATED
    assert engine.start().status is ProductionSafetyStatus.MONITORING
    assert isinstance(engine._lock, RLock().__class__)

    healthy = engine.evaluate(safety_input())
    assert healthy.decision is SafetyDecision.ALLOW

    locked = engine.activate_global_kill_switch(ManualSafetyCommand(NOW, SafetyScope.GLOBAL, None, "halt"))
    assert locked.global_locked is True
    recovery = engine.request_recovery(safety_input())
    assert recovery.recovery.decision is RecoveryDecision.MANUAL_RELEASE_REQUIRED
    released = engine.release_global_kill_switch(timestamp=NOW + timedelta(seconds=1), reason="safe")
    assert released.status is ProductionSafetyStatus.MONITORING
    assert engine.stop().status is ProductionSafetyStatus.STOPPED


def started_engine():
    engine = ProductionSafetyV1Engine()
    engine.start()
    return engine


def global_command(timestamp):
    return ManualSafetyCommand(
        timestamp,
        SafetyScope.GLOBAL,
        None,
        "manual emergency stop",
    )


def test_manual_global_kill_switch_returns_consistent_locked_snapshot():
    engine = started_engine()
    healthy = engine.evaluate(safety_input())

    result = engine.activate_global_kill_switch(
        global_command(healthy.timestamp + timedelta(minutes=1))
    )

    assert result.status is ProductionSafetyStatus.LOCKED
    assert result.change is SafetyChange.GLOBAL_LOCKED
    assert result.decision is SafetyDecision.BLOCK_GLOBAL
    assert result.severity is SafetySeverity.CRITICAL
    assert result.global_locked is True
    assert result.degraded is False
    assert result.automatic_lock_count == 0

    evaluation = next(
        item
        for item in result.evaluations
        if item.rule is SafetyRuleType.MANUAL_KILL_SWITCH
        and item.scope is SafetyScope.GLOBAL
    )

    assert evaluation.result is SafetyRuleResult.FAILED
    assert evaluation.decision is SafetyDecision.BLOCK_GLOBAL
    assert evaluation.severity is SafetySeverity.CRITICAL

    incident = next(
        item
        for item in result.open_incidents
        if item.rule is SafetyRuleType.MANUAL_KILL_SWITCH
        and item.scope is SafetyScope.GLOBAL
    )

    assert incident.status is SafetyIncidentStatus.OPEN
    assert incident.manual_release_required is True
    assert result.recovery.decision is RecoveryDecision.MANUAL_RELEASE_REQUIRED
    assert result.recovery.global_recovery_ready is False


def test_repeated_global_kill_activation_is_idempotent():
    engine = started_engine()
    healthy = engine.evaluate(safety_input())

    first = engine.activate_global_kill_switch(
        global_command(healthy.timestamp + timedelta(minutes=1))
    )
    count = first.manual_kill_count

    second = engine.activate_global_kill_switch(
        global_command(healthy.timestamp + timedelta(minutes=1))
    )

    assert second.manual_kill_count == count
    assert second.decision is SafetyDecision.BLOCK_GLOBAL
    assert second.global_locked is True


def test_releasing_manual_global_lock_does_not_clear_other_global_failure():
    engine = started_engine()

    global_locked = engine.evaluate(safety_input(realized=-250.0))
    assert global_locked.decision is SafetyDecision.BLOCK_GLOBAL

    engine.activate_global_kill_switch(
        global_command(global_locked.timestamp + timedelta(minutes=1))
    )

    released = engine.release_global_kill_switch(
        timestamp=global_locked.timestamp + timedelta(minutes=2),
        reason="manual condition cleared",
    )

    assert released.status is ProductionSafetyStatus.LOCKED
    assert released.decision is SafetyDecision.BLOCK_GLOBAL
    assert released.global_locked is True

    assert any(
        item.rule is SafetyRuleType.DAILY_LOSS_LIMIT
        and item.status is SafetyIncidentStatus.OPEN
        for item in released.open_incidents
    )
