import pytest

from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import EXECUTION_DRY_RUN_ACKNOWLEDGED, EXECUTION_INTENT_CREATED
from application.execution_runtime_v1 import ExecutionIntentStatus, ExecutionRuntimeStatus, ExecutionRuntimeV1, ExecutionRuntimeV1Configuration
from tests.test_risk_management_v2_calculator import calculate, risk_input, strategy


def runtime(**kwargs):
    return ExecutionRuntimeV1(instrument=Instrument.NIFTY, configuration=ExecutionRuntimeV1Configuration(maximum_open_intents=1), **kwargs)


def test_constructor_start_stop_submit_duplicate_fill_cancel_counters_snapshot_history_clear():
    events = []
    bus = EventBus()
    bus.subscribe(EXECUTION_INTENT_CREATED, lambda payload: events.append("created"))
    bus.subscribe(EXECUTION_DRY_RUN_ACKNOWLEDGED, lambda payload: events.append("ack"))
    item = runtime(event_bus=bus)
    risk = calculate(risk_input(proposed_invalidation_price=83.0, proposed_objective_price=148.0))

    assert item.snapshot().runtime_status is ExecutionRuntimeStatus.CREATED
    assert item.start().running is True
    result = item.submit(risk)
    assert result.intent.status is ExecutionIntentStatus.ACKNOWLEDGED
    with pytest.raises(RuntimeError):
        item.submit(risk)
    partial = item.confirm_fill(fill_quantity=1, fill_price=100.0)
    assert partial.filled_quantity == 1
    final = item.confirm_fill(fill_quantity=partial.remaining_quantity, fill_price=110.0)
    assert final.intent.status is ExecutionIntentStatus.FILLED
    assert item.submit(risk) is final
    snapshot = item.snapshot()
    assert snapshot.submitted_count == 1
    assert snapshot.acknowledged_count == 1
    assert snapshot.fill_count == 1
    assert item.history()
    assert events == ["created", "ack"]
    item.stop()
    assert item.clear().runtime_status is ExecutionRuntimeStatus.CLEARED


def test_wrong_instrument_running_required_cancel_and_stop_with_open_intent():
    item = runtime()
    risk = calculate()
    with pytest.raises(RuntimeError):
        item.submit(risk)
    item.start()
    item.submit(risk)
    with pytest.raises(RuntimeError):
        item.stop()
    item.cancel_active()
    item.stop()
    other = ExecutionRuntimeV1(instrument=Instrument.BANKNIFTY)
    other.start()
    with pytest.raises(ValueError):
        other.submit(calculate())
    with pytest.raises(ValueError):
        ExecutionRuntimeV1(instrument=Instrument.SBI)
