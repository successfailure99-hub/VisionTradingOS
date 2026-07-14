from dataclasses import replace

from application.execution_runtime_v1 import ExecutionDecision, ExecutionFillPolicy, ExecutionRuntimeV1, ExecutionRuntimeV1Configuration
from core.enums.instrument import Instrument
from engines.position_management_v1 import PositionManagementV1Configuration, PositionSourceValidator
from tests.test_position_management_v1_models import filled_execution
from tests.test_risk_management_v2_calculator import calculate, risk_input


def test_full_and_partial_fill_accepted_and_unfilled_rejected():
    full = filled_execution()
    risk = calculate(risk_input(proposed_invalidation_price=83.0, proposed_objective_price=148.0))
    runtime = ExecutionRuntimeV1(instrument=Instrument.NIFTY)
    runtime.start()
    unfilled = runtime.submit(risk)
    partial_runtime = ExecutionRuntimeV1(
        instrument=Instrument.NIFTY,
        configuration=ExecutionRuntimeV1Configuration(fill_policy=ExecutionFillPolicy.IMMEDIATE_PARTIAL, require_manual_fill_confirmation=True),
    )
    partial_runtime.start()
    partial = partial_runtime.submit(risk)

    validator = PositionSourceValidator()
    assert validator.validate(full, PositionManagementV1Configuration())[0] is True
    assert validator.validate(partial, PositionManagementV1Configuration())[0] is True
    assert validator.validate(unfilled, PositionManagementV1Configuration())[0] is False


def test_rejected_cancelled_zero_fill_live_flags_and_input_not_mutated():
    full = filled_execution()
    validator = PositionSourceValidator()
    before = full
    rejected = replace(full, decision=ExecutionDecision.REJECTED, filled_quantity=0, average_fill_price=None)
    live_intent = object.__new__(type(full.intent))
    for field in full.intent.__dataclass_fields__:
        object.__setattr__(live_intent, field, getattr(full.intent, field))
    object.__setattr__(live_intent, "dry_run", False)
    live = replace(full, intent=live_intent)

    assert validator.validate(rejected, PositionManagementV1Configuration())[0] is False
    assert validator.validate(live, PositionManagementV1Configuration())[0] is False
    assert full == before
