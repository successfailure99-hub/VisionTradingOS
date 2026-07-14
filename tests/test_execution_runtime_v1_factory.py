from core.enums.instrument import Instrument
from core.event_bus import EventBus
from application.execution_runtime_v1 import ExecutionRuntimeStatus, ExecutionRuntimeV1Configuration, ExecutionRuntimeV1Factory


def test_factory_creates_one_unstarted_runtime_and_reuses_dependencies():
    bus = EventBus()
    clock_calls = []

    def clock():
        from tests.test_strategy_decision_v2_integration import NOW

        clock_calls.append(1)
        return NOW

    runtime = ExecutionRuntimeV1Factory().create(
        instrument=Instrument.NIFTY,
        configuration=ExecutionRuntimeV1Configuration(),
        event_bus=bus,
        clock=clock,
    )

    assert runtime.snapshot().runtime_status is ExecutionRuntimeStatus.CREATED
    assert runtime.snapshot().running is False
    assert clock_calls
