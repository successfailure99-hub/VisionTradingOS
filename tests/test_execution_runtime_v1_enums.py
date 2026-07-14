from application.execution_runtime_v1 import (
    ExecutionChange,
    ExecutionDecision,
    ExecutionFillPolicy,
    ExecutionIntentStatus,
    ExecutionOrderType,
    ExecutionRuntimeStatus,
    ExecutionSide,
)


def test_exact_enum_values_and_exports():
    assert ExecutionRuntimeStatus.CREATED.value == "created"
    assert ExecutionRuntimeStatus.RUNNING.value == "running"
    assert ExecutionDecision.ACCEPTED.value == "accepted"
    assert ExecutionDecision.INSUFFICIENT_DATA.value == "insufficient_data"
    assert ExecutionSide.BUY.value == "buy"
    assert ExecutionOrderType.LIMIT.value == "limit"
    assert ExecutionIntentStatus.SUBMITTED_DRY_RUN.value == "submitted_dry_run"
    assert ExecutionFillPolicy.MANUAL_CONFIRMATION.value == "manual_confirmation"
    assert ExecutionChange.ACKNOWLEDGED.value == "acknowledged"
