import pytest

from application.execution_runtime_v1 import (
    DryRunExecutionSimulator,
    ExecutionFillPolicy,
    ExecutionIntentStatus,
    ExecutionRuntimeV1Configuration,
    intent_from_risk,
)
from tests.test_risk_management_v2_calculator import calculate, risk_input


def intent():
    risk = calculate(risk_input(proposed_invalidation_price=83.0, proposed_objective_price=148.0))
    return intent_from_risk(risk, created_at=risk.timestamp, order_type=ExecutionRuntimeV1Configuration().order_type)


def test_manual_submit_immediate_full_and_immediate_partial():
    item = intent()
    simulator = DryRunExecutionSimulator()
    manual = simulator.submit(item, ExecutionRuntimeV1Configuration(), timestamp=item.created_at)
    full = simulator.submit(item, ExecutionRuntimeV1Configuration(fill_policy=ExecutionFillPolicy.IMMEDIATE_FULL, require_manual_fill_confirmation=True), timestamp=item.created_at)
    partial = simulator.submit(item, ExecutionRuntimeV1Configuration(fill_policy=ExecutionFillPolicy.IMMEDIATE_PARTIAL, require_manual_fill_confirmation=True), timestamp=item.created_at)

    assert manual.intent.status is ExecutionIntentStatus.ACKNOWLEDGED
    assert full.intent.status is ExecutionIntentStatus.FILLED
    assert partial.intent.status in {ExecutionIntentStatus.PARTIALLY_FILLED, ExecutionIntentStatus.FILLED}


def test_partial_then_full_weighted_average_and_invalid_overfill():
    item = intent()
    simulator = DryRunExecutionSimulator()
    prior = simulator.submit(item, ExecutionRuntimeV1Configuration(), timestamp=item.created_at)
    partial = simulator.confirm_fill(prior.intent, fill_quantity=1, fill_price=100.0, timestamp=item.created_at, prior_result=prior)
    final = simulator.confirm_fill(partial.intent, fill_quantity=partial.remaining_quantity, fill_price=110.0, timestamp=item.created_at, prior_result=partial)

    assert final.intent.status is ExecutionIntentStatus.FILLED
    assert final.average_fill_price >= 100.0
    with pytest.raises(ValueError):
        simulator.confirm_fill(final.intent, fill_quantity=1, fill_price=100.0, timestamp=item.created_at, prior_result=final)


def test_cancel_and_reject_cancel_after_fill_immutability():
    item = intent()
    simulator = DryRunExecutionSimulator()
    prior = simulator.submit(item, ExecutionRuntimeV1Configuration(), timestamp=item.created_at)
    cancelled = simulator.cancel(prior.intent, timestamp=item.created_at, prior_result=prior)
    full = simulator.submit(item, ExecutionRuntimeV1Configuration(fill_policy=ExecutionFillPolicy.IMMEDIATE_FULL, require_manual_fill_confirmation=True), timestamp=item.created_at)

    assert cancelled.intent.status is ExecutionIntentStatus.CANCELLED
    assert prior.intent.status is ExecutionIntentStatus.ACKNOWLEDGED
    with pytest.raises(ValueError):
        simulator.cancel(full.intent, timestamp=item.created_at, prior_result=full)
