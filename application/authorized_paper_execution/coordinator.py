"""
Synchronous Authorized Paper Execution Handoff V1.
"""

from __future__ import annotations

from core import events
from core.base_engine import BaseEngine
from engines.paper_execution_coordinator.enums import PaperExecutionDecision, PaperExecutionStatus
from engines.paper_execution_coordinator.models import PaperExecutionReceipt, PaperExecutionRequest
from engines.strategy.enums import TradeDirection
from engines.trade_decision_authorization.enums import TradeAuthorizationDecision
from engines.trade_decision_authorization.models import TradeAuthorizationResult
from engines.trade_execution_policy.enums import (
    ExecutionDecisionStatus,
    ExecutionMode,
    ExecutionPlanStatus,
    ExecutionReasonCode,
    ExecutionRoutingTarget,
)
from engines.trade_execution_policy.models import TradeExecutionPlan

from .enums import (
    AuthorizedPaperHandoffDecision,
    AuthorizedPaperHandoffLifecycle,
    AuthorizedPaperHandoffReason,
)
from .models import (
    AuthorizedPaperHandoffRequest,
    AuthorizedPaperHandoffResult,
    AuthorizedPaperHandoffSnapshot,
)


MAX_AUTHORIZATION_AGE_SECONDS = 120
_REASON_PRIORITY = (
    AuthorizedPaperHandoffReason.INVALID_INPUT,
    AuthorizedPaperHandoffReason.INSTRUMENT_MISMATCH,
    AuthorizedPaperHandoffReason.DIRECTION_MISMATCH,
    AuthorizedPaperHandoffReason.PLAN_MISMATCH,
    AuthorizedPaperHandoffReason.STALE_AUTHORIZATION,
    AuthorizedPaperHandoffReason.STALE_EXECUTION_PLAN,
    AuthorizedPaperHandoffReason.PLAN_NOT_PAPER,
    AuthorizedPaperHandoffReason.PLAN_NOT_EXECUTABLE,
    AuthorizedPaperHandoffReason.AUTHORIZATION_BLOCKED,
    AuthorizedPaperHandoffReason.AUTHORIZATION_REDUCED,
    AuthorizedPaperHandoffReason.DUPLICATE_EXECUTION,
    AuthorizedPaperHandoffReason.PAPER_EXECUTION_FAILED,
    AuthorizedPaperHandoffReason.AUTHORIZED,
)


class AuthorizedPaperExecutionCoordinator(BaseEngine):
    """
    Gates already-authorized paper execution plans into the existing coordinator.
    """

    def __init__(self, event_bus, *, orchestrator):
        super().__init__(event_bus)
        self._orchestrator = orchestrator
        self._lifecycle_state = AuthorizedPaperHandoffLifecycle.CREATED
        self._results: dict[str, AuthorizedPaperHandoffResult] = {}
        self._fingerprints: dict[str, str] = {}
        self._invoked_plan_ids: set[str] = set()
        self._last_result: AuthorizedPaperHandoffResult | None = None
        self._handoff_count = 0
        self._executed_count = 0
        self._held_count = 0
        self._rejected_count = 0
        self._failed_paper_execution_count = 0
        self._paper_execution_call_count = 0

    def start(self) -> AuthorizedPaperHandoffSnapshot:
        if self._lifecycle_state is AuthorizedPaperHandoffLifecycle.CREATED:
            self._lifecycle_state = AuthorizedPaperHandoffLifecycle.READY
        self._publish_state()
        return self.snapshot()

    def handoff(self, request: AuthorizedPaperHandoffRequest) -> AuthorizedPaperHandoffResult:
        if self._lifecycle_state in {
            AuthorizedPaperHandoffLifecycle.STOPPED,
            AuthorizedPaperHandoffLifecycle.FAILED,
        }:
            if not isinstance(request, AuthorizedPaperHandoffRequest):
                raise TypeError("request must be AuthorizedPaperHandoffRequest")
            reason = (
                AuthorizedPaperHandoffReason.INVALID_INPUT
                if self._lifecycle_state is AuthorizedPaperHandoffLifecycle.FAILED
                else AuthorizedPaperHandoffReason.PLAN_NOT_EXECUTABLE
            )
            return self._store_result(request, self._rejected_result(request, (reason,)))
        if not isinstance(request, AuthorizedPaperHandoffRequest):
            raise TypeError("request must be AuthorizedPaperHandoffRequest")
        if self._lifecycle_state is AuthorizedPaperHandoffLifecycle.CREATED:
            raise RuntimeError("authorized paper handoff coordinator must be started")

        fingerprint = request.fingerprint()
        stored = self._results.get(request.handoff_id)
        if stored is not None:
            if self._fingerprints[request.handoff_id] != fingerprint:
                raise ValueError("handoff_id already exists for different request")
            return stored

        try:
            result = self._handoff(request)
        except Exception:
            self._lifecycle_state = AuthorizedPaperHandoffLifecycle.FAILED
            self._event_bus.publish(events.AUTHORIZED_PAPER_HANDOFF_FAILED, self.snapshot())
            self._publish_state()
            raise
        return self._store_result(request, result)

    def get_result(self, handoff_id: str) -> AuthorizedPaperHandoffResult | None:
        if not isinstance(handoff_id, str):
            return None
        return self._results.get(handoff_id.strip())

    def snapshot(self) -> AuthorizedPaperHandoffSnapshot:
        return AuthorizedPaperHandoffSnapshot(
            enabled=True,
            lifecycle_state=self._lifecycle_state,
            handoff_count=self._handoff_count,
            executed_count=self._executed_count,
            held_count=self._held_count,
            rejected_count=self._rejected_count,
            failed_paper_execution_count=self._failed_paper_execution_count,
            last_result=self._last_result,
            paper_execution_call_count=self._paper_execution_call_count,
            broker_order_calls=0,
            live_order_submission_enabled=False,
        )

    def stop(self) -> AuthorizedPaperHandoffSnapshot:
        if self._lifecycle_state in {
            AuthorizedPaperHandoffLifecycle.READY,
            AuthorizedPaperHandoffLifecycle.ACTIVE,
        }:
            self._lifecycle_state = AuthorizedPaperHandoffLifecycle.STOPPED
            self._publish_state()
        return self.snapshot()

    def reset(self) -> AuthorizedPaperHandoffSnapshot:
        self._results.clear()
        self._fingerprints.clear()
        self._invoked_plan_ids.clear()
        self._last_result = None
        self._data = None
        self._handoff_count = 0
        self._executed_count = 0
        self._held_count = 0
        self._rejected_count = 0
        self._failed_paper_execution_count = 0
        self._paper_execution_call_count = 0
        self._lifecycle_state = AuthorizedPaperHandoffLifecycle.READY
        self._publish_state()
        return self.snapshot()

    def _handoff(self, request: AuthorizedPaperHandoffRequest) -> AuthorizedPaperHandoffResult:
        authorization = request.authorization_result
        plan = request.execution_plan
        if not isinstance(authorization, TradeAuthorizationResult) or not isinstance(plan, TradeExecutionPlan):
            return self._rejected_result(request, (AuthorizedPaperHandoffReason.INVALID_INPUT,))
        if request.instrument.value != authorization.instrument.value or request.instrument.value != plan.instrument:
            return self._rejected_result(request, (AuthorizedPaperHandoffReason.INSTRUMENT_MISMATCH,))
        if authorization.direction is not plan.direction:
            return self._rejected_result(request, (AuthorizedPaperHandoffReason.DIRECTION_MISMATCH,))
        if authorization.source_policy_id != plan.execution_plan_id:
            return self._rejected_result(request, (AuthorizedPaperHandoffReason.PLAN_MISMATCH,))

        reasons = []
        if (request.timestamp - authorization.timestamp).total_seconds() > MAX_AUTHORIZATION_AGE_SECONDS:
            reasons.append(AuthorizedPaperHandoffReason.STALE_AUTHORIZATION)
        if request.timestamp < plan.valid_from or request.timestamp >= plan.valid_until:
            reasons.append(AuthorizedPaperHandoffReason.STALE_EXECUTION_PLAN)
        if plan.execution_mode is not ExecutionMode.PAPER or plan.routing_target is not ExecutionRoutingTarget.PAPER_TRADING:
            reasons.append(AuthorizedPaperHandoffReason.PLAN_NOT_PAPER)
        if not _plan_is_executable(plan):
            reasons.append(AuthorizedPaperHandoffReason.PLAN_NOT_EXECUTABLE)
        if authorization.decision is TradeAuthorizationDecision.BLOCK:
            reasons.append(AuthorizedPaperHandoffReason.AUTHORIZATION_BLOCKED)
        elif authorization.decision is TradeAuthorizationDecision.REDUCE:
            reasons.append(AuthorizedPaperHandoffReason.AUTHORIZATION_REDUCED)
        elif authorization.decision is TradeAuthorizationDecision.AUTHORIZE and authorization.authorization_multiplier != 1.0:
            reasons.append(AuthorizedPaperHandoffReason.INVALID_INPUT)
        if plan.execution_plan_id in self._invoked_plan_ids:
            reasons.append(AuthorizedPaperHandoffReason.DUPLICATE_EXECUTION)
        reasons = _ordered_unique(tuple(reasons))
        if reasons:
            return self._rejected_result(request, reasons)
        return self._execute(request, authorization, plan)

    def _execute(
        self,
        request: AuthorizedPaperHandoffRequest,
        authorization: TradeAuthorizationResult,
        plan: TradeExecutionPlan,
    ) -> AuthorizedPaperHandoffResult:
        paper_request = PaperExecutionRequest(
            request_id=request.handoff_id,
            timestamp=request.timestamp,
            instrument=request.instrument,
            execution_plan=plan,
            correlation_id=request.correlation_id,
        )
        self._paper_execution_call_count += 1
        try:
            receipt = self._orchestrator.execute_paper_plan(request.instrument, paper_request)
        except (TypeError, ValueError, RuntimeError):
            self._failed_paper_execution_count += 1
            self._invoked_plan_ids.add(plan.execution_plan_id)
            return self._result(
                request,
                authorization,
                plan,
                AuthorizedPaperHandoffDecision.REJECT,
                (AuthorizedPaperHandoffReason.PAPER_EXECUTION_FAILED,),
                paper_execution_invoked=True,
                paper_execution_result=None,
            )
        if not isinstance(receipt, PaperExecutionReceipt) or receipt.decision is not PaperExecutionDecision.APPROVED or receipt.status in {
            PaperExecutionStatus.REJECTED,
            PaperExecutionStatus.EXPIRED,
            PaperExecutionStatus.FAILED,
            PaperExecutionStatus.CANCELLED,
        }:
            self._failed_paper_execution_count += 1
            self._invoked_plan_ids.add(plan.execution_plan_id)
            return self._result(
                request,
                authorization,
                plan,
                AuthorizedPaperHandoffDecision.REJECT,
                (AuthorizedPaperHandoffReason.PAPER_EXECUTION_FAILED,),
                paper_execution_invoked=True,
                paper_execution_result=receipt if isinstance(receipt, PaperExecutionReceipt) else None,
            )
        self._invoked_plan_ids.add(plan.execution_plan_id)
        return self._result(
            request,
            authorization,
            plan,
            AuthorizedPaperHandoffDecision.EXECUTE,
            (AuthorizedPaperHandoffReason.AUTHORIZED,),
            paper_execution_invoked=True,
            paper_execution_result=receipt,
        )

    def _rejected_result(
        self,
        request: AuthorizedPaperHandoffRequest,
        reasons: tuple[AuthorizedPaperHandoffReason, ...],
    ) -> AuthorizedPaperHandoffResult:
        authorization = request.authorization_result if isinstance(request.authorization_result, TradeAuthorizationResult) else None
        plan = request.execution_plan if isinstance(request.execution_plan, TradeExecutionPlan) else None
        decision = (
            AuthorizedPaperHandoffDecision.HOLD_REDUCTION_REQUIRED
            if reasons[0] is AuthorizedPaperHandoffReason.AUTHORIZATION_REDUCED
            else AuthorizedPaperHandoffDecision.REJECT
        )
        return self._result(
            request,
            authorization,
            plan,
            decision,
            reasons,
            paper_execution_invoked=False,
            paper_execution_result=None,
        )

    def _result(
        self,
        request: AuthorizedPaperHandoffRequest,
        authorization: TradeAuthorizationResult | None,
        plan: TradeExecutionPlan | None,
        decision: AuthorizedPaperHandoffDecision,
        reasons: tuple[AuthorizedPaperHandoffReason, ...],
        *,
        paper_execution_invoked: bool,
        paper_execution_result: PaperExecutionReceipt | None,
    ) -> AuthorizedPaperHandoffResult:
        ordered = _ordered_unique(reasons)
        direction = _direction(authorization, plan)
        return AuthorizedPaperHandoffResult(
            handoff_id=request.handoff_id,
            timestamp=request.timestamp,
            instrument=request.instrument,
            direction=direction,
            decision=decision,
            primary_reason=ordered[0],
            reasons=ordered,
            paper_execution_invoked=paper_execution_invoked,
            paper_execution_call_count=1 if paper_execution_invoked else 0,
            paper_execution_result=paper_execution_result,
            authorization_id=None if authorization is None else authorization.authorization_id,
            execution_plan_id=None if plan is None else plan.execution_plan_id,
            correlation_id=request.correlation_id,
            broker_order_calls=0,
            live_order_submission_enabled=False,
        )

    def _store_result(
        self,
        request: AuthorizedPaperHandoffRequest,
        result: AuthorizedPaperHandoffResult,
    ) -> AuthorizedPaperHandoffResult:
        self._results[request.handoff_id] = result
        self._fingerprints[request.handoff_id] = request.fingerprint()
        self._last_result = result
        self._data = result
        self._handoff_count += 1
        if result.decision is AuthorizedPaperHandoffDecision.EXECUTE:
            self._executed_count += 1
        elif result.decision is AuthorizedPaperHandoffDecision.HOLD_REDUCTION_REQUIRED:
            self._held_count += 1
        else:
            self._rejected_count += 1
        if self._lifecycle_state is AuthorizedPaperHandoffLifecycle.READY:
            self._lifecycle_state = AuthorizedPaperHandoffLifecycle.ACTIVE
        self._event_bus.publish(events.AUTHORIZED_PAPER_HANDOFF_COMPLETED, result)
        if result.decision is AuthorizedPaperHandoffDecision.EXECUTE:
            self._event_bus.publish(events.AUTHORIZED_PAPER_HANDOFF_EXECUTED, result)
        elif result.decision is AuthorizedPaperHandoffDecision.HOLD_REDUCTION_REQUIRED:
            self._event_bus.publish(events.AUTHORIZED_PAPER_HANDOFF_HELD, result)
        else:
            self._event_bus.publish(events.AUTHORIZED_PAPER_HANDOFF_REJECTED, result)
        self._publish_state()
        return result

    def _publish_state(self) -> None:
        self._event_bus.publish(events.AUTHORIZED_PAPER_HANDOFF_STATE_UPDATED, self.snapshot())


def _plan_is_executable(plan: TradeExecutionPlan) -> bool:
    return (
        plan.status is ExecutionPlanStatus.READY_FOR_PAPER
        and plan.decision_status is ExecutionDecisionStatus.APPROVED
        and plan.primary_reason is ExecutionReasonCode.APPROVED
        and plan.broker_submission_allowed is False
        and plan.broker_order_calls == 0
    )


def _direction(
    authorization: TradeAuthorizationResult | None,
    plan: TradeExecutionPlan | None,
) -> TradeDirection:
    if authorization is not None:
        return authorization.direction
    if plan is not None:
        return plan.direction
    return TradeDirection.NONE


def _ordered_unique(reasons: tuple[AuthorizedPaperHandoffReason, ...]) -> tuple[AuthorizedPaperHandoffReason, ...]:
    seen = set()
    ordered = []
    for reason in _REASON_PRIORITY:
        if reason in reasons and reason not in seen:
            ordered.append(reason)
            seen.add(reason)
    return tuple(ordered)
