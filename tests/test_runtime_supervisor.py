from application import ApplicationBootstrap
from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration, RuntimeDependencyReadiness
from application.runtime_supervisor import RuntimeSupervisor, RuntimeSupervisorCheck, RuntimeSupervisorSnapshot


def lifecycle():
    item = ApplicationBootstrap(RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,))).create_application()
    item.start()
    return item


def test_runtime_supervisor_models_are_immutable_and_validate_text():
    check = RuntimeSupervisorCheck("RuntimeSnapshot", "SymbolRuntime", "snapshot", "Dashboard", "READY")
    snapshot = RuntimeSupervisorSnapshot("READY", 500, (check,))

    assert check.healthy is True
    assert snapshot.checks == (check,)
    assert snapshot.interval_ms == 500


def test_runtime_supervisor_observes_canonical_runtime_snapshot_without_new_owner():
    subject = RuntimeSupervisor(lifecycle())

    result = subject.check()
    checks = {item.stage: item for item in result.checks}

    assert checks["RuntimeSnapshot"].owner == "SymbolRuntime"
    assert checks["RuntimeContract"].producer == "RuntimeContractValidator"
    assert checks["RuntimeIntegrity"].owner == "SymbolRuntime"
    assert "Dashboard" in checks
    assert subject.last_snapshot == result


def test_runtime_supervisor_invokes_existing_recovery_hook_for_missing_vision_state():
    calls = []
    subject = RuntimeSupervisor(lifecycle(), recovery_handlers={"Vision Method": lambda: calls.append("vision")})

    result = subject.monitor()

    assert calls == ["vision"]
    assert result.recovery_actions == ("Vision Method: Recalculate Vision Method through the existing live bridge.",)


def test_runtime_supervisor_treats_supporting_liquidity_readiness_as_degraded_not_failed():
    item = lifecycle()
    runtime = item.orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    original_snapshot = item.orchestrator.snapshot()
    base = original_snapshot.runtime_snapshots[0]
    degraded = RuntimeDependencyReadiness(
        component="Liquidity Input History",
        criticality="SUPPORTING",
        status="INSUFFICIENT",
        reason="insufficient candles for liquidity context",
        owner="SymbolRuntime",
        producer="Vision Liquidity",
        consumer="Vision Structure Events",
        dependency="Vision Decision History",
        instrument=RuntimeInstrument.NIFTY,
        timeframe="5m",
        trading_date=None,
        timestamp=None,
        history_count=2,
        minimum_required_count=3,
        exception_class="ValueError",
        exception_message="insufficient candles for liquidity context",
        recovery_state="CHECKPOINT_ACTIVE",
    )
    from dataclasses import replace

    snapshot = replace(base, liquidity_input_readiness=degraded)
    lifecycle_snapshot = replace(original_snapshot, runtime_snapshots=(snapshot,))
    result = RuntimeSupervisor(item).check(replace(item.snapshot(), orchestrator_snapshot=lifecycle_snapshot))
    checks = {check.stage: check for check in result.checks}

    assert checks["Liquidity Input History"].status == "DEGRADED"
    assert result.status != "FAILED"
    assert runtime is item.orchestrator.get_runtime(RuntimeInstrument.NIFTY)
