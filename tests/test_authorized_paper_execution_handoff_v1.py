from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from application.authorized_paper_execution import (
    AuthorizedPaperExecutionCoordinator,
    AuthorizedPaperHandoffDecision,
    AuthorizedPaperHandoffLifecycle,
    AuthorizedPaperHandoffReason,
    AuthorizedPaperHandoffRequest,
    AuthorizedPaperHandoffResult,
    AuthorizedPaperHandoffSnapshot,
)
from core.event_bus import EventBus
from core import events
from engines.order_management.enums import OrderSide, OrderType
from engines.paper_execution_coordinator import PaperExecutionDecision, PaperExecutionStatus
from engines.paper_execution_coordinator.models import PaperExecutionReceipt
from engines.strategy.enums import TradeDirection
from engines.trade_decision_authorization import (
    TradeAuthorizationDecision,
    TradeAuthorizationReason,
    TradeAuthorizationResult,
)
from engines.trade_execution_policy import ExecutionMode
from engines.trade_execution_policy.enums import (
    ExecutionDecisionStatus,
    ExecutionPlanStatus,
    ExecutionReasonCode,
    ExecutionRoutingTarget,
)
from engines.trade_execution_policy.models import TradeExecutionPlan


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 7, 21, 10, 0, tzinfo=IST)


class FakeOrchestrator:
    def __init__(self, *, receipt=None, error=None):
        self.receipt = receipt
        self.error = error
        self.calls = 0
        self.requests = []
        self.strategy_calls = 0
        self.confidence_calibration_calls = 0
        self.risk_evaluation_calls = 0
        self.execution_policy_evaluation_calls = 0
        self.authorization_recalculation_calls = 0
        self.place_order_calls = 0
        self.modify_order_calls = 0
        self.cancel_order_calls = 0
        self.direct_position_mutation_calls = 0
        self.network_calls = 0
        self.mutation_calls = 0
        self.broker_order_calls = 0
        self.live_order_submission_enabled = False

    def execute_paper_plan(self, instrument, request):
        self.calls += 1
        self.requests.append((instrument, request))
        if self.error is not None:
            raise self.error
        return self.receipt or receipt(request.execution_plan)


def plan(**overrides):
    values = {
        "execution_plan_id": "plan-1",
        "created_at": NOW,
        "valid_from": NOW,
        "valid_until": NOW + timedelta(minutes=5),
        "instrument": "NIFTY",
        "direction": TradeDirection.BULLISH,
        "entry_side": OrderSide.BUY,
        "execution_mode": ExecutionMode.PAPER,
        "entry_order_type": OrderType.LIMIT,
        "entry_quantity": 75,
        "entry_limit_price": 100.0,
        "entry_trigger_price": None,
        "market_reference_price": 100.0,
        "risk_decision_id": "risk-1",
        "risk_decision_fingerprint": "risk-fp",
        "signal_id": "signal-1",
        "strategy_id": "strategy-1",
        "client_request_id": "client-1",
        "stop_plan": None,
        "target_plan": None,
        "manual_approval_required": False,
        "manual_approval_present": True,
        "routing_target": ExecutionRoutingTarget.PAPER_TRADING,
        "status": ExecutionPlanStatus.READY_FOR_PAPER,
        "decision_status": ExecutionDecisionStatus.APPROVED,
        "primary_reason": ExecutionReasonCode.APPROVED,
        "findings": (),
        "policy_fingerprint": "policy-fp",
        "request_fingerprint": "request-fp",
        "input_fingerprint": "input-fp",
    }
    values.update(overrides)
    return TradeExecutionPlan(**values)


def authorization(execution_plan=None, **overrides):
    execution_plan = execution_plan or plan()
    values = {
        "authorization_id": "auth-1",
        "timestamp": NOW,
        "instrument": RuntimeInstrument.NIFTY,
        "direction": execution_plan.direction,
        "decision": TradeAuthorizationDecision.AUTHORIZE,
        "primary_reason": TradeAuthorizationReason.AUTHORIZED,
        "reasons": (TradeAuthorizationReason.AUTHORIZED,),
        "authorization_multiplier": 1.0,
        "stale_inputs": (),
        "invalid_inputs": (),
        "source_strategy_id": "strategy-1",
        "source_confidence_id": "confidence-1",
        "source_risk_id": execution_plan.risk_decision_id,
        "source_policy_id": execution_plan.execution_plan_id,
    }
    values.update(overrides)
    return TradeAuthorizationResult(**values)


def request(execution_plan=None, authorization_result=None, **overrides):
    execution_plan = execution_plan or plan()
    authorization_result = authorization_result or authorization(execution_plan)
    values = {
        "handoff_id": "handoff-1",
        "timestamp": NOW + timedelta(seconds=30),
        "instrument": RuntimeInstrument.NIFTY,
        "authorization_result": authorization_result,
        "execution_plan": execution_plan,
        "correlation_id": "corr-1",
    }
    values.update(overrides)
    return AuthorizedPaperHandoffRequest(**values)


def receipt(execution_plan=None, **overrides):
    execution_plan = execution_plan or plan()
    values = {
        "receipt_id": "receipt-1",
        "created_at": NOW + timedelta(seconds=30),
        "updated_at": NOW + timedelta(seconds=30),
        "instrument": execution_plan.instrument,
        "execution_plan_id": execution_plan.execution_plan_id,
        "execution_plan_fingerprint": execution_plan.input_fingerprint,
        "request_fingerprint": "paper-request-fp",
        "entry_order": None,
        "stop_order": None,
        "target_order": None,
        "paper_submission_id": "paper-submission-1",
        "stop_paper_submission_id": None,
        "target_paper_submission_id": None,
        "status": PaperExecutionStatus.ENTRY_SUBMITTED,
        "decision": PaperExecutionDecision.APPROVED,
        "primary_reason": "approved",
        "findings": (),
        "entry_filled_quantity": 0,
        "remaining_quantity": execution_plan.entry_quantity,
        "broker_submission_allowed": False,
        "broker_order_calls": 0,
        "order_management_request_count": 1,
        "paper_submission_count": 1,
    }
    values.update(overrides)
    from engines.paper_execution_coordinator import PaperExecutionReasonCode

    if isinstance(values["primary_reason"], str):
        values["primary_reason"] = PaperExecutionReasonCode(values["primary_reason"])
    return PaperExecutionReceipt(**values)


def coordinator(fake=None, bus=None):
    fake = fake or FakeOrchestrator()
    item = AuthorizedPaperExecutionCoordinator(bus or EventBus(), orchestrator=fake)
    item.start()
    return item, fake


def execute_valid(item=None, fake=None, req=None):
    item, fake = (item, fake) if item is not None else coordinator(fake)
    return item.handoff(req or request()), item, fake


def assert_no_unsafe_calls(fake):
    assert fake.strategy_calls == 0
    assert fake.confidence_calibration_calls == 0
    assert fake.risk_evaluation_calls == 0
    assert fake.execution_policy_evaluation_calls == 0
    assert fake.authorization_recalculation_calls == 0
    assert fake.place_order_calls == 0
    assert fake.modify_order_calls == 0
    assert fake.cancel_order_calls == 0
    assert fake.direct_position_mutation_calls == 0
    assert fake.network_calls == 0
    assert fake.mutation_calls == 0
    assert fake.broker_order_calls == 0
    assert fake.live_order_submission_enabled is False


def test_models_are_immutable_and_validate_safety_invariants():
    req = request()
    result = AuthorizedPaperHandoffResult(
        handoff_id="result-1",
        timestamp=req.timestamp,
        instrument=RuntimeInstrument.NIFTY,
        direction=TradeDirection.BULLISH,
        decision=AuthorizedPaperHandoffDecision.REJECT,
        primary_reason=AuthorizedPaperHandoffReason.INVALID_INPUT,
        reasons=[AuthorizedPaperHandoffReason.INVALID_INPUT],
        paper_execution_invoked=False,
        paper_execution_call_count=0,
        paper_execution_result=None,
        authorization_id="auth-1",
        execution_plan_id="plan-1",
    )
    snapshot = AuthorizedPaperHandoffSnapshot(
        enabled=True,
        lifecycle_state=AuthorizedPaperHandoffLifecycle.CREATED,
        handoff_count=0,
        executed_count=0,
        held_count=0,
        rejected_count=0,
        failed_paper_execution_count=0,
        last_result=None,
        paper_execution_call_count=0,
    )

    with pytest.raises(FrozenInstanceError):
        req.handoff_id = "changed"
    with pytest.raises(FrozenInstanceError):
        result.decision = AuthorizedPaperHandoffDecision.EXECUTE
    with pytest.raises(FrozenInstanceError):
        snapshot.enabled = False
    assert result.reasons == (AuthorizedPaperHandoffReason.INVALID_INPUT,)
    with pytest.raises(ValueError, match="paper_execution_call_count"):
        replace(result, paper_execution_call_count=2)
    with pytest.raises(ValueError, match="broker_order_calls"):
        replace(result, broker_order_calls=1)
    with pytest.raises(ValueError, match="broker_order_calls"):
        replace(snapshot, broker_order_calls=1)


def test_request_validation_requires_aware_time_supported_instrument_and_no_future_sources():
    with pytest.raises(ValueError, match="timezone-aware"):
        request(timestamp=datetime(2026, 7, 21, 10, 0))
    with pytest.raises(ValueError, match="unsupported instrument"):
        request(instrument="FINNIFTY")
    with pytest.raises(ValueError, match="authorization_result timestamp"):
        request(authorization_result=authorization(timestamp=NOW + timedelta(minutes=1)))
    future_plan = plan(created_at=NOW + timedelta(minutes=1), valid_from=NOW + timedelta(minutes=1), valid_until=NOW + timedelta(minutes=2))
    future_plan_request = request(execution_plan=future_plan, authorization_result=authorization(future_plan), timestamp=NOW)
    assert future_plan_request.execution_plan is future_plan


def test_lifecycle_transitions_and_expected_outcomes_do_not_fail_lifecycle():
    fake = FakeOrchestrator()
    item = AuthorizedPaperExecutionCoordinator(EventBus(), orchestrator=fake)
    assert item.snapshot().lifecycle_state is AuthorizedPaperHandoffLifecycle.CREATED
    assert item.start().lifecycle_state is AuthorizedPaperHandoffLifecycle.READY
    first = item.handoff(request())
    assert first.decision is AuthorizedPaperHandoffDecision.EXECUTE
    assert item.snapshot().lifecycle_state is AuthorizedPaperHandoffLifecycle.ACTIVE
    second_plan = plan(execution_plan_id="plan-2", risk_decision_id="risk-2")
    item.handoff(request(handoff_id="handoff-2", execution_plan=second_plan, authorization_result=authorization(second_plan, authorization_id="auth-2")))
    assert item.snapshot().lifecycle_state is AuthorizedPaperHandoffLifecycle.ACTIVE
    assert item.stop().lifecycle_state is AuthorizedPaperHandoffLifecycle.STOPPED
    with pytest.raises(RuntimeError, match="authorized paper handoff coordinator is stopped"):
        item.handoff(request(handoff_id="handoff-stopped"))
    assert item.snapshot().lifecycle_state is AuthorizedPaperHandoffLifecycle.STOPPED
    assert item.reset().lifecycle_state is AuthorizedPaperHandoffLifecycle.READY

    reduced = item.handoff(request(authorization_result=authorization(decision=TradeAuthorizationDecision.REDUCE, primary_reason=TradeAuthorizationReason.POLICY_REDUCED, reasons=(TradeAuthorizationReason.POLICY_REDUCED,), authorization_multiplier=0.5), handoff_id="reduce"))
    assert reduced.decision is AuthorizedPaperHandoffDecision.HOLD_REDUCTION_REQUIRED
    assert item.snapshot().lifecycle_state is AuthorizedPaperHandoffLifecycle.ACTIVE
    item._lifecycle_state = AuthorizedPaperHandoffLifecycle.FAILED
    with pytest.raises(RuntimeError, match="authorized paper handoff coordinator is failed"):
        item.handoff(request(handoff_id="failed-state"))
    assert item.snapshot().lifecycle_state is AuthorizedPaperHandoffLifecycle.FAILED
    assert item.reset().lifecycle_state is AuthorizedPaperHandoffLifecycle.READY


def test_terminal_lifecycle_handoff_raises_without_state_counters_events_or_paper_calls():
    bus = EventBus()
    business_events = []
    for event_name in (
        events.AUTHORIZED_PAPER_HANDOFF_COMPLETED,
        events.AUTHORIZED_PAPER_HANDOFF_EXECUTED,
        events.AUTHORIZED_PAPER_HANDOFF_HELD,
        events.AUTHORIZED_PAPER_HANDOFF_REJECTED,
        events.AUTHORIZED_PAPER_HANDOFF_FAILED,
        events.AUTHORIZED_PAPER_HANDOFF_STATE_UPDATED,
    ):
        bus.subscribe(event_name, lambda payload, event_name=event_name: business_events.append((event_name, payload)))
    item, fake = coordinator(bus=bus)
    item.stop()
    business_events.clear()
    before = item.snapshot()

    with pytest.raises(RuntimeError, match="authorized paper handoff coordinator is stopped"):
        item.handoff(request(handoff_id="stopped-handoff"))

    stopped = item.snapshot()
    assert stopped.lifecycle_state is AuthorizedPaperHandoffLifecycle.STOPPED
    assert stopped.handoff_count == before.handoff_count
    assert stopped.rejected_count == before.rejected_count
    assert stopped.paper_execution_call_count == before.paper_execution_call_count
    assert item.get_result("stopped-handoff") is None
    assert business_events == []
    assert fake.calls == 0
    assert item.reset().lifecycle_state is AuthorizedPaperHandoffLifecycle.READY
    valid_after_stopped_reset = item.handoff(request(handoff_id="valid-after-stopped-reset"))
    assert valid_after_stopped_reset.decision is AuthorizedPaperHandoffDecision.EXECUTE

    item._lifecycle_state = AuthorizedPaperHandoffLifecycle.FAILED
    business_events.clear()
    fake.calls = 0
    before_failed = item.snapshot()
    with pytest.raises(RuntimeError, match="authorized paper handoff coordinator is failed"):
        item.handoff(request(handoff_id="failed-handoff"))

    failed = item.snapshot()
    assert failed.lifecycle_state is AuthorizedPaperHandoffLifecycle.FAILED
    assert failed.handoff_count == before_failed.handoff_count
    assert failed.executed_count == before_failed.executed_count
    assert failed.held_count == before_failed.held_count
    assert failed.rejected_count == before_failed.rejected_count
    assert failed.paper_execution_call_count == before_failed.paper_execution_call_count
    assert item.get_result("failed-handoff") is None
    assert business_events == []
    assert fake.calls == 0
    assert item.reset().lifecycle_state is AuthorizedPaperHandoffLifecycle.READY
    next_plan = plan(execution_plan_id="plan-after-failed-reset", risk_decision_id="risk-after-failed-reset")
    valid_after_failed_reset = item.handoff(
        request(
            handoff_id="valid-after-failed-reset",
            execution_plan=next_plan,
            authorization_result=authorization(next_plan, authorization_id="auth-after-failed-reset"),
        )
    )
    assert valid_after_failed_reset.decision is AuthorizedPaperHandoffDecision.EXECUTE
    assert item.snapshot().broker_order_calls == 0
    assert item.snapshot().live_order_submission_enabled is False


def test_authorize_invokes_public_paper_facade_once_and_preserves_plan_identity_and_values():
    original_plan = plan(entry_quantity=150, entry_order_type=OrderType.STOP_LIMIT, entry_limit_price=101.0, entry_trigger_price=100.5)
    req = request(execution_plan=original_plan, authorization_result=authorization(original_plan))
    result, item, fake = execute_valid(req=req)

    assert result.decision is AuthorizedPaperHandoffDecision.EXECUTE
    assert result.primary_reason is AuthorizedPaperHandoffReason.AUTHORIZED
    assert result.paper_execution_invoked is True
    assert result.paper_execution_call_count == 1
    assert fake.calls == 1
    assert item.snapshot().paper_execution_call_count == 1
    _, paper_request = fake.requests[0]
    assert paper_request.execution_plan is original_plan
    assert paper_request.execution_plan.entry_quantity == 150
    assert paper_request.execution_plan.entry_order_type is OrderType.STOP_LIMIT
    assert paper_request.execution_plan.entry_limit_price == 101.0
    assert paper_request.execution_plan.entry_trigger_price == 100.5
    assert paper_request.execution_plan.execution_plan_id == original_plan.execution_plan_id
    assert_no_unsafe_calls(fake)


@pytest.mark.parametrize(
    ("decision", "multiplier", "expected_decision", "expected_reason"),
    (
        (TradeAuthorizationDecision.REDUCE, 0.5, AuthorizedPaperHandoffDecision.HOLD_REDUCTION_REQUIRED, AuthorizedPaperHandoffReason.AUTHORIZATION_REDUCED),
        (TradeAuthorizationDecision.BLOCK, 0.0, AuthorizedPaperHandoffDecision.REJECT, AuthorizedPaperHandoffReason.AUTHORIZATION_BLOCKED),
    ),
)
def test_reduce_and_block_never_invoke_paper_or_change_quantity(decision, multiplier, expected_decision, expected_reason):
    execution_plan = plan(entry_quantity=75)
    auth = authorization(
        execution_plan,
        decision=decision,
        authorization_multiplier=multiplier,
        primary_reason=TradeAuthorizationReason.POLICY_REDUCED if decision is TradeAuthorizationDecision.REDUCE else TradeAuthorizationReason.POLICY_BLOCKED,
        reasons=(TradeAuthorizationReason.POLICY_REDUCED if decision is TradeAuthorizationDecision.REDUCE else TradeAuthorizationReason.POLICY_BLOCKED,),
    )
    result, _, fake = execute_valid(req=request(execution_plan=execution_plan, authorization_result=auth))

    assert result.decision is expected_decision
    assert result.primary_reason is expected_reason
    assert result.paper_execution_result is None
    assert fake.calls == 0
    assert execution_plan.entry_quantity == 75


@pytest.mark.parametrize(
    ("req", "reason"),
    (
        (lambda: request(authorization_result=object()), AuthorizedPaperHandoffReason.INVALID_INPUT),
        (lambda: request(instrument=RuntimeInstrument.BANKNIFTY), AuthorizedPaperHandoffReason.INSTRUMENT_MISMATCH),
        (lambda: request(execution_plan=plan(direction=TradeDirection.BEARISH), authorization_result=authorization(direction=TradeDirection.BULLISH)), AuthorizedPaperHandoffReason.DIRECTION_MISMATCH),
        (lambda: request(authorization_result=authorization(source_policy_id="other-plan")), AuthorizedPaperHandoffReason.PLAN_MISMATCH),
    ),
)
def test_source_consistency_rejections_do_not_invoke_paper(req, reason):
    result, _, fake = execute_valid(req=req())
    assert result.decision is AuthorizedPaperHandoffDecision.REJECT
    assert result.primary_reason is reason
    assert fake.calls == 0


def test_missing_plan_linkage_rejects_and_directions_are_unchanged():
    execution_plan = plan(direction=TradeDirection.BEARISH, entry_side=OrderSide.SELL)
    auth = authorization(execution_plan, direction=TradeDirection.BEARISH, source_policy_id=None)
    result, _, fake = execute_valid(req=request(execution_plan=execution_plan, authorization_result=auth))

    assert result.primary_reason is AuthorizedPaperHandoffReason.PLAN_MISMATCH
    assert result.direction is TradeDirection.BEARISH
    assert execution_plan.direction is TradeDirection.BEARISH
    assert auth.direction is TradeDirection.BEARISH
    assert fake.calls == 0


def test_freshness_uses_request_timestamp_without_wall_clock():
    fresh = request()
    stale_auth = request(authorization_result=authorization(timestamp=NOW - timedelta(seconds=121)), handoff_id="stale-auth")
    future_plan = plan(created_at=NOW + timedelta(minutes=2), valid_from=NOW + timedelta(minutes=2), valid_until=NOW + timedelta(minutes=5))
    expired_plan = plan(execution_plan_id="expired-plan", valid_until=NOW + timedelta(seconds=30))

    assert execute_valid(req=fresh)[0].decision is AuthorizedPaperHandoffDecision.EXECUTE
    assert execute_valid(req=stale_auth)[0].primary_reason is AuthorizedPaperHandoffReason.STALE_AUTHORIZATION
    assert execute_valid(req=request(execution_plan=future_plan, authorization_result=authorization(future_plan), timestamp=NOW + timedelta(minutes=1), handoff_id="future-plan"))[0].primary_reason is AuthorizedPaperHandoffReason.STALE_EXECUTION_PLAN
    assert execute_valid(req=request(execution_plan=expired_plan, authorization_result=authorization(expired_plan), handoff_id="expired-plan"))[0].primary_reason is AuthorizedPaperHandoffReason.STALE_EXECUTION_PLAN


@pytest.mark.parametrize(
    "execution_plan",
    (
        plan(execution_mode=ExecutionMode.PLAN_ONLY, routing_target=ExecutionRoutingTarget.PLAN_ONLY),
        plan(status=ExecutionPlanStatus.AWAITING_MANUAL_APPROVAL),
        plan(status=ExecutionPlanStatus.LOCKED),
        plan(status=ExecutionPlanStatus.REJECTED),
        plan(status=ExecutionPlanStatus.EXPIRED),
        plan(status=ExecutionPlanStatus.CANCELLED),
        plan(decision_status=ExecutionDecisionStatus.INVALID),
    ),
)
def test_non_paper_and_non_executable_plans_are_rejected(execution_plan):
    result, _, fake = execute_valid(req=request(execution_plan=execution_plan, authorization_result=authorization(execution_plan)))
    assert result.decision is AuthorizedPaperHandoffDecision.REJECT
    assert result.primary_reason in {
        AuthorizedPaperHandoffReason.PLAN_NOT_PAPER,
        AuthorizedPaperHandoffReason.PLAN_NOT_EXECUTABLE,
    }
    assert fake.calls == 0


def test_authorize_requires_multiplier_one():
    auth = authorization()
    object.__setattr__(auth, "authorization_multiplier", 0.5)
    result, _, fake = execute_valid(req=request(authorization_result=auth))
    assert result.primary_reason is AuthorizedPaperHandoffReason.INVALID_INPUT
    assert fake.calls == 0


def test_duplicate_request_idempotency_and_duplicate_plan_safety():
    bus = EventBus()
    completed = []
    bus.subscribe(events.AUTHORIZED_PAPER_HANDOFF_COMPLETED, completed.append)
    item, fake = coordinator(bus=bus)
    req = request()
    first = item.handoff(req)
    duplicate = item.handoff(req)

    assert duplicate is first
    assert item.snapshot().handoff_count == 1
    assert fake.calls == 1
    assert len(completed) == 1
    with pytest.raises(ValueError, match="different request"):
        item.handoff(request(timestamp=NOW + timedelta(seconds=31)))
    second = item.handoff(request(handoff_id="handoff-2"))
    assert second.primary_reason is AuthorizedPaperHandoffReason.DUPLICATE_EXECUTION
    assert fake.calls == 1


def test_held_and_rejected_unexecuted_plans_can_be_resubmitted_when_corrected():
    item, fake = coordinator()
    reduced_auth = authorization(decision=TradeAuthorizationDecision.REDUCE, authorization_multiplier=0.5, primary_reason=TradeAuthorizationReason.POLICY_REDUCED, reasons=(TradeAuthorizationReason.POLICY_REDUCED,))
    held = item.handoff(request(handoff_id="held", authorization_result=reduced_auth))
    authorized = item.handoff(request(handoff_id="authorized-after-held"))

    bad_auth = authorization(source_policy_id="wrong")
    rejected = item.handoff(request(handoff_id="rejected", authorization_result=bad_auth))
    corrected = item.handoff(request(handoff_id="corrected", execution_plan=plan(execution_plan_id="plan-2"), authorization_result=authorization(plan(execution_plan_id="plan-2"))))

    assert held.decision is AuthorizedPaperHandoffDecision.HOLD_REDUCTION_REQUIRED
    assert rejected.primary_reason is AuthorizedPaperHandoffReason.PLAN_MISMATCH
    assert authorized.decision is AuthorizedPaperHandoffDecision.EXECUTE
    assert corrected.decision is AuthorizedPaperHandoffDecision.EXECUTE
    assert fake.calls == 2


def test_downstream_expected_failure_maps_to_rejection_without_retry_or_failed_lifecycle():
    result, item, fake = execute_valid(fake=FakeOrchestrator(error=ValueError("paper failure")))
    assert result.decision is AuthorizedPaperHandoffDecision.REJECT
    assert result.primary_reason is AuthorizedPaperHandoffReason.PAPER_EXECUTION_FAILED
    assert result.paper_execution_invoked is True
    assert result.paper_execution_call_count == 1
    assert fake.calls == 1
    assert item.snapshot().failed_paper_execution_count == 1
    assert item.snapshot().lifecycle_state is AuthorizedPaperHandoffLifecycle.ACTIVE


def test_downstream_failed_receipt_maps_to_rejection_without_retry():
    failed_receipt = receipt(status=PaperExecutionStatus.FAILED, decision=PaperExecutionDecision.INVALID)
    result, item, fake = execute_valid(fake=FakeOrchestrator(receipt=failed_receipt))
    assert result.primary_reason is AuthorizedPaperHandoffReason.PAPER_EXECUTION_FAILED
    assert result.paper_execution_result is failed_receipt
    assert fake.calls == 1
    assert item.snapshot().failed_paper_execution_count == 1


def test_orchestrator_owns_one_handoff_coordinator_and_exposes_snapshot():
    app = ApplicationOrchestrator(EventBus(), RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.SENSEX)))
    app.start()

    assert app.authorized_paper_execution_coordinator._orchestrator is app
    assert app.get_authorized_paper_handoff_snapshot().lifecycle_state is AuthorizedPaperHandoffLifecycle.READY
    snapshot = app.snapshot()
    assert snapshot.authorized_paper_handoff == app.get_authorized_paper_handoff_snapshot()
    assert not hasattr(app.authorized_paper_execution_coordinator, "paper_execution_coordinator")
    assert app.reset_authorized_paper_handoff().lifecycle_state is AuthorizedPaperHandoffLifecycle.READY


def test_orchestrator_rejects_cross_instrument_handoff_request():
    app = ApplicationOrchestrator(EventBus(), RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,)))
    app.start()
    with pytest.raises(ValueError, match="RuntimeInstrument is not configured"):
        app.handoff_authorized_paper_execution(request(instrument=RuntimeInstrument.BANKNIFTY))


def test_safety_search_terms_are_absent_from_handoff_package():
    from pathlib import Path

    root = Path("application/authorized_paper_execution")
    text = "\n".join(path.read_text() for path in root.glob("*.py"))
    for forbidden in (
        "place_order",
        "modify_order",
        "cancel_order",
        "run_strategy",
        "calibrate(",
        "evaluate_risk",
        "evaluate_policy",
        "threading",
        "asyncio",
        "time.sleep",
        "QTimer",
        "requests",
        "httpx",
        "EventBus(",
    ):
        assert forbidden not in text
    assert "reconcile" not in text
