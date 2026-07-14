from dataclasses import replace

from application.execution_runtime_v1 import ExecutionDecision, ExecutionIntentStatus, ExecutionRuntimeStatus, ExecutionRuntimeV1
from core.enums.instrument import Instrument
from engines.risk_management_v2.enums import RiskDecision
from tests.test_risk_management_v2_calculator import account, calculate, risk_input, strategy


def test_created_running_acknowledged_partial_filled_cancelled_transitions():
    runtime = ExecutionRuntimeV1(instrument=Instrument.NIFTY)
    risk = calculate(risk_input(proposed_invalidation_price=83.0, proposed_objective_price=148.0))

    assert runtime.snapshot().runtime_status is ExecutionRuntimeStatus.CREATED
    runtime.start()
    assert runtime.snapshot().runtime_status is ExecutionRuntimeStatus.RUNNING
    submitted = runtime.submit(risk)
    assert [event.status for event in submitted.lifecycle][-1] is ExecutionIntentStatus.ACKNOWLEDGED
    partial = runtime.confirm_fill(fill_quantity=1, fill_price=100.0)
    assert partial.intent.status is ExecutionIntentStatus.PARTIALLY_FILLED
    filled = runtime.confirm_fill(fill_quantity=partial.remaining_quantity, fill_price=100.0)
    assert filled.intent.status is ExecutionIntentStatus.FILLED

    risk2 = calculate(risk_input(strategy(minutes=1)))
    cancelled_runtime = ExecutionRuntimeV1(instrument=Instrument.NIFTY)
    cancelled_runtime.start()
    cancelled_runtime.submit(risk2)
    assert cancelled_runtime.cancel_active().intent.status is ExecutionIntentStatus.CANCELLED


def test_rejected_wait_and_insufficient_inputs():
    runtime = ExecutionRuntimeV1(instrument=Instrument.NIFTY)
    runtime.start()
    rejected = calculate(risk_input(account=account(realized_pnl_today=-300.0)))
    wait = replace(rejected, decision=RiskDecision.WAIT)
    insufficient = replace(rejected, decision=RiskDecision.INSUFFICIENT_DATA)

    assert runtime.submit(rejected).decision is ExecutionDecision.REJECTED
    assert runtime.submit(wait).decision is ExecutionDecision.WAIT
    assert runtime.submit(insufficient).decision is ExecutionDecision.INSUFFICIENT_DATA
