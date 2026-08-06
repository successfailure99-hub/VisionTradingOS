from application import ApplicationBootstrap
from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration
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
