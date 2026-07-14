from dataclasses import FrozenInstanceError, replace

import pytest

from application.execution_runtime_v1 import (
    ExecutionDecision,
    ExecutionIntent,
    ExecutionIntentStatus,
    ExecutionLifecycleEvent,
    ExecutionOrderType,
    ExecutionResult,
    ExecutionRuntimeStatus,
    ExecutionRuntimeV1Snapshot,
    ExecutionSide,
    build_intent_id,
    intent_from_risk,
    side_from_risk,
)
from tests.test_risk_management_v2_calculator import calculate, risk_input, strategy


def approved_risk():
    return calculate()


def test_intent_consistency_side_mapping_and_deterministic_id():
    risk = approved_risk()
    intent = intent_from_risk(risk, created_at=risk.timestamp, order_type=ExecutionOrderType.LIMIT)

    assert intent.intent_id == build_intent_id(risk)
    assert side_from_risk(risk) is ExecutionSide.BUY
    assert intent.quantity == risk.approved_quantity
    assert intent.dry_run is True
    assert intent.analysis_only is True
    assert "order_id" not in intent.__dataclass_fields__
    with pytest.raises(FrozenInstanceError):
        intent.quantity = 2
    with pytest.raises(ValueError):
        ExecutionIntent(**{**{field: getattr(intent, field) for field in intent.__dataclass_fields__}, "quantity": intent.quantity + 1})


def test_lifecycle_result_and_runtime_snapshot_rules():
    risk = approved_risk()
    intent = intent_from_risk(risk, created_at=risk.timestamp, order_type=ExecutionOrderType.LIMIT)
    event = ExecutionLifecycleEvent(1, risk.timestamp, ExecutionIntentStatus.ACKNOWLEDGED, "Acknowledged.", 0, intent.quantity, None)
    result = ExecutionResult(ExecutionDecision.ACCEPTED, replace(intent, status=ExecutionIntentStatus.ACKNOWLEDGED), (event,), intent.quantity, 0, intent.quantity, None, "Accepted.")
    snapshot = ExecutionRuntimeV1Snapshot(risk.instrument, risk.timestamp, ExecutionRuntimeStatus.RUNNING, ExecutionDecision.ACCEPTED, result.intent, result, 1, 1, 0, 0, 0, 0, 1, True, True, 1, None)

    assert snapshot.running is True
    assert result.lifecycle == (event,)
    with pytest.raises(ValueError):
        ExecutionRuntimeV1Snapshot(risk.instrument, risk.timestamp, ExecutionRuntimeStatus.STOPPED, ExecutionDecision.ACCEPTED, None, result, 0, 0, 0, 0, 0, 0, 0, True, True, 1, None)


def test_rejected_risk_cannot_create_intent_and_no_credentials():
    rejected = calculate(risk_input(strategy(), account=__import__("tests.test_risk_management_v2_calculator", fromlist=["account"]).account(realized_pnl_today=-300.0)))

    with pytest.raises(ValueError):
        intent_from_risk(rejected, created_at=rejected.timestamp, order_type=ExecutionOrderType.LIMIT)
    assert not any("credential" in field or "account_id" in field for field in ExecutionIntent.__dataclass_fields__)
