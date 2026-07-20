"""
Synchronous Paper Execution Coordinator V1.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from core import events
from core.base_engine import BaseEngine
from engines.order_management.enums import OrderCommandType, OrderSide, OrderStatus, OrderType, ProductType
from engines.order_management.models import OrderCommand, OrderRequest, OrderSnapshot, OrderState
from engines.order_management.order_management_engine import OrderManagementEngine
from engines.paper_trading.engine import PaperTradingEngine
from engines.risk.enums import RiskDecision, RiskRejectionReason, RiskReductionReason, RiskTier
from engines.risk.models import RiskDecisionState
from engines.trade_execution_policy.enums import (
    ExecutionDecisionStatus,
    ExecutionMode,
    ExecutionPlanStatus,
    ExecutionReasonCode,
    ExecutionRoutingTarget,
    ProtectiveOrderPurpose,
)
from engines.trade_execution_policy.models import ProtectiveOrderPlan, TradeExecutionPlan
from engines.paper_execution_coordinator.enums import (
    CoordinatedOrderPurpose,
    CoordinatorLifecycleState,
    PaperExecutionDecision,
    PaperExecutionReasonCode,
    PaperExecutionSeverity,
    PaperExecutionStatus,
)
from engines.paper_execution_coordinator.models import (
    CoordinatedOrderReference,
    PaperExecutionCoordinatorPolicy,
    PaperExecutionCoordinatorSnapshot,
    PaperExecutionFinding,
    PaperExecutionReceipt,
    PaperExecutionRequest,
    finding_identity,
    receipt_identity,
)


ACTIVE_STATUSES = {
    PaperExecutionStatus.ENTRY_SUBMITTED,
    PaperExecutionStatus.ENTRY_PARTIALLY_FILLED,
    PaperExecutionStatus.ENTRY_FILLED,
    PaperExecutionStatus.PROTECTIVE_ORDERS_CREATED,
    PaperExecutionStatus.ACTIVE,
}

TERMINAL_STATUSES = {
    PaperExecutionStatus.COMPLETED,
    PaperExecutionStatus.CANCELLED,
    PaperExecutionStatus.REJECTED,
    PaperExecutionStatus.EXPIRED,
    PaperExecutionStatus.FAILED,
}


class PaperExecutionCoordinator(BaseEngine):
    """
    Coordinates approved paper execution plans through existing boundaries.

    The coordinator does not place broker orders, evaluate strategy or risk, or
    create positions. It translates an already approved paper execution plan
    into Order Management requests and Paper Trading submissions.
    """

    def __init__(
        self,
        event_bus,
        *,
        instrument: str,
        timeframe: str,
        order_management_engine: OrderManagementEngine,
        paper_trading_engine: PaperTradingEngine,
        exchange: str = "NSE",
        policy: PaperExecutionCoordinatorPolicy | None = None,
    ):
        super().__init__(event_bus)
        if not isinstance(order_management_engine, OrderManagementEngine):
            raise TypeError("order_management_engine must be OrderManagementEngine")
        if not isinstance(paper_trading_engine, PaperTradingEngine):
            raise TypeError("paper_trading_engine must be PaperTradingEngine")
        self._instrument = _instrument(instrument)
        self._timeframe = _text(timeframe, "timeframe")
        self._exchange = _text(exchange, "exchange").upper()
        self._order_engine = order_management_engine
        self._paper_engine = paper_trading_engine
        self._policy = policy or PaperExecutionCoordinatorPolicy()
        if not isinstance(self._policy, PaperExecutionCoordinatorPolicy):
            raise TypeError("policy must be PaperExecutionCoordinatorPolicy")
        self._state = CoordinatorLifecycleState.CREATED
        self._receipts: dict[str, PaperExecutionReceipt] = {}
        self._by_plan_id: dict[str, str] = {}
        self._plan_fingerprints: dict[str, str] = {}
        self._by_plan_fingerprint: dict[str, str] = {}
        self._by_request_id: dict[str, str] = {}
        self._request_fingerprints: dict[str, str] = {}
        self._by_order_id: dict[str, str] = {}
        self._request_id_by_receipt: dict[str, str] = {}
        self._latest_plan_by_receipt: dict[str, TradeExecutionPlan] = {}
        self._last_receipt: PaperExecutionReceipt | None = None
        self._findings: tuple[PaperExecutionFinding, ...] = ()
        self._evaluation_count = 0
        self._approved_count = 0
        self._rejected_count = 0
        self._duplicate_count = 0
        self._expired_count = 0
        self._failed_count = 0
        self._order_management_request_count = 0
        self._paper_submission_count = 0

    @property
    def last_receipt(self) -> PaperExecutionReceipt | None:
        return self._last_receipt

    def start(self) -> PaperExecutionCoordinatorSnapshot:
        if self._state is not CoordinatorLifecycleState.STOPPED:
            self._state = CoordinatorLifecycleState.READY
        self._publish(events.PAPER_EXECUTION_COORDINATOR_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def stop(self) -> PaperExecutionCoordinatorSnapshot:
        self._state = CoordinatorLifecycleState.STOPPED
        self._publish(events.PAPER_EXECUTION_COORDINATOR_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def execute(
        self,
        request: PaperExecutionRequest,
        policy: PaperExecutionCoordinatorPolicy | None = None,
    ) -> PaperExecutionReceipt:
        if not isinstance(request, PaperExecutionRequest):
            raise TypeError("request must be PaperExecutionRequest")
        active_policy = policy or self._policy
        if not isinstance(active_policy, PaperExecutionCoordinatorPolicy):
            raise TypeError("policy must be PaperExecutionCoordinatorPolicy")
        self._evaluation_count += 1
        if self._state is CoordinatorLifecycleState.CREATED:
            self._state = CoordinatorLifecycleState.READY

        failure = self._eligibility_failure(request, active_policy)
        if failure is not None:
            receipt = failure
            self._store_terminal(receipt)
            self._publish_terminal(receipt)
            return receipt

        duplicate = self._duplicate_receipt(request, active_policy)
        if duplicate is not None:
            self._duplicate_count += 1
            self._publish(events.PAPER_EXECUTION_DUPLICATE, duplicate)
            self._publish(events.PAPER_EXECUTION_EVALUATED, duplicate)
            return duplicate

        try:
            receipt = self._create_entry(request, active_policy)
        except ExpectedCoordinationError as exc:
            receipt = self._rejected_receipt(request, active_policy, exc.reason, str(exc), exc.field_name, exc.observed, exc.expected)
            self._store_terminal(receipt)
            self._publish_terminal(receipt)
            return receipt
        except Exception as exc:
            self._state = CoordinatorLifecycleState.FAILED
            receipt = self._rejected_receipt(
                request,
                active_policy,
                PaperExecutionReasonCode.INTERNAL_COORDINATION_ERROR,
                _safe_message(exc),
                decision=PaperExecutionDecision.INVALID,
                status=PaperExecutionStatus.FAILED,
                severity=PaperExecutionSeverity.CRITICAL,
            )
            self._store_terminal(receipt)
            self._publish(events.PAPER_EXECUTION_FAILED, receipt)
            self._publish(events.PAPER_EXECUTION_EVALUATED, receipt)
            self._publish(events.PAPER_EXECUTION_COORDINATOR_STATE_UPDATED, self.snapshot())
            return receipt

        if receipt.decision is not PaperExecutionDecision.APPROVED:
            self._store_terminal(receipt)
            self._publish_terminal(receipt)
            return receipt
        self._approved_count += 1
        self._state = CoordinatorLifecycleState.ACTIVE
        self._store_active(receipt)
        self._publish(events.PAPER_EXECUTION_ACCEPTED, receipt)
        self._publish(events.PAPER_ENTRY_ORDER_CREATED, receipt)
        self._publish(events.PAPER_ENTRY_SUBMITTED, receipt)
        self._publish(events.PAPER_EXECUTION_EVALUATED, receipt)
        self._publish(events.PAPER_EXECUTION_COORDINATOR_STATE_UPDATED, self.snapshot())
        return receipt

    def on_order_update(self, order_update, *, timestamp: datetime) -> PaperExecutionReceipt | None:
        _aware(timestamp, "timestamp")
        if not isinstance(order_update, OrderState):
            raise TypeError("order_update must be OrderState")
        receipt_id = self._by_order_id.get(order_update.client_order_id)
        if receipt_id is None:
            return None
        receipt = self._receipts[receipt_id]
        if receipt.status in TERMINAL_STATUSES:
            return receipt
        if order_update.filled_quantity < receipt.entry_filled_quantity:
            failed = self._transition(
                receipt,
                timestamp,
                PaperExecutionStatus.FAILED,
                PaperExecutionDecision.INVALID,
                PaperExecutionReasonCode.INCONSISTENT_ORDER_STATE,
                self._finding(timestamp, PaperExecutionSeverity.ERROR, PaperExecutionReasonCode.INCONSISTENT_ORDER_STATE, "Fill quantity cannot decrease.", "filled_quantity", order_update.filled_quantity, receipt.entry_filled_quantity),
            )
            self._store_terminal(failed)
            self._publish(events.PAPER_EXECUTION_FAILED, failed)
            return failed
        if order_update.filled_quantity > order_update.quantity:
            failed = self._transition(
                receipt,
                timestamp,
                PaperExecutionStatus.FAILED,
                PaperExecutionDecision.INVALID,
                PaperExecutionReasonCode.INCONSISTENT_ORDER_STATE,
                self._finding(timestamp, PaperExecutionSeverity.ERROR, PaperExecutionReasonCode.INCONSISTENT_ORDER_STATE, "Fill quantity cannot exceed order quantity.", "filled_quantity", order_update.filled_quantity, order_update.quantity),
            )
            self._store_terminal(failed)
            self._publish(events.PAPER_EXECUTION_FAILED, failed)
            return failed
        if order_update.status is OrderStatus.CANCELLED:
            cancelled = replace(receipt, updated_at=timestamp, status=PaperExecutionStatus.CANCELLED, decision=PaperExecutionDecision.REJECTED, primary_reason=PaperExecutionReasonCode.CANCELLED)
            self._store_terminal(cancelled)
            self._publish(events.PAPER_EXECUTION_CANCELLED, cancelled)
            return cancelled
        if order_update.status is OrderStatus.REJECTED:
            rejected = replace(receipt, updated_at=timestamp, status=PaperExecutionStatus.REJECTED, decision=PaperExecutionDecision.REJECTED, primary_reason=PaperExecutionReasonCode.PAPER_SUBMISSION_FAILED)
            self._store_terminal(rejected)
            self._publish(events.PAPER_EXECUTION_REJECTED, rejected)
            return rejected
        if order_update.status is OrderStatus.PARTIALLY_FILLED:
            updated = replace(receipt, updated_at=timestamp, status=PaperExecutionStatus.ENTRY_PARTIALLY_FILLED, entry_filled_quantity=order_update.filled_quantity, remaining_quantity=order_update.remaining_quantity)
            self._store_active(updated)
            self._publish(events.PAPER_ENTRY_PARTIALLY_FILLED, updated)
            return updated
        if order_update.status is OrderStatus.FILLED:
            filled = replace(receipt, updated_at=timestamp, status=PaperExecutionStatus.ENTRY_FILLED, entry_filled_quantity=order_update.filled_quantity, remaining_quantity=0)
            if filled.stop_order is None and filled.target_order is None:
                filled = self._create_protective_orders(filled, order_update, timestamp)
            self._store_active(filled)
            self._publish(events.PAPER_ENTRY_FILLED, filled)
            if filled.stop_order is not None or filled.target_order is not None:
                self._publish(events.PAPER_PROTECTIVE_ORDERS_CREATED, filled)
            return filled
        return receipt

    def cancel(self, receipt_id: str, *, timestamp: datetime, reason: str = "cancelled") -> PaperExecutionReceipt:
        _aware(timestamp, "timestamp")
        rid = _text(receipt_id, "receipt_id")
        receipt = self._receipts.get(rid)
        if receipt is None:
            raise ValueError("Unknown paper execution receipt.")
        if receipt.status is PaperExecutionStatus.COMPLETED:
            raise ValueError("Completed paper execution cannot be cancelled.")
        if receipt.status in {PaperExecutionStatus.CANCELLED, PaperExecutionStatus.REJECTED, PaperExecutionStatus.EXPIRED, PaperExecutionStatus.FAILED}:
            return receipt
        for order in (receipt.entry_order, receipt.stop_order, receipt.target_order):
            if order is not None:
                state = self._order_engine.get_order(order.order_id)
                if state is not None and state.status not in {OrderStatus.CANCELLED, OrderStatus.FILLED, OrderStatus.REJECTED}:
                    self._order_engine.apply(OrderCommand(OrderCommandType.CANCEL, order.order_id, timestamp))
        if hasattr(self._paper_engine, "cancel_managed_order") and receipt.entry_order is not None:
            self._paper_engine.cancel_managed_order(receipt.entry_order.order_id, timestamp=timestamp, reason=reason)
        cancelled = replace(receipt, updated_at=timestamp, status=PaperExecutionStatus.CANCELLED, decision=PaperExecutionDecision.REJECTED, primary_reason=PaperExecutionReasonCode.CANCELLED)
        self._store_terminal(cancelled)
        self._publish(events.PAPER_EXECUTION_CANCELLED, cancelled)
        self._publish(events.PAPER_EXECUTION_COORDINATOR_STATE_UPDATED, self.snapshot())
        return cancelled

    def reset_session(self) -> PaperExecutionCoordinatorSnapshot:
        self._receipts.clear()
        self._by_plan_id.clear()
        self._plan_fingerprints.clear()
        self._by_plan_fingerprint.clear()
        self._by_request_id.clear()
        self._request_fingerprints.clear()
        self._by_order_id.clear()
        self._request_id_by_receipt.clear()
        self._latest_plan_by_receipt.clear()
        self._last_receipt = None
        self._findings = ()
        self._state = CoordinatorLifecycleState.READY
        self._publish(events.PAPER_EXECUTION_COORDINATOR_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def snapshot(self) -> PaperExecutionCoordinatorSnapshot:
        active = tuple(receipt.receipt_id for receipt in self._receipts.values() if receipt.status in ACTIVE_STATUSES)
        return PaperExecutionCoordinatorSnapshot(
            enabled=self._policy.enabled,
            lifecycle_state=self._state,
            last_receipt=self._last_receipt,
            evaluation_count=self._evaluation_count,
            approved_count=self._approved_count,
            rejected_count=self._rejected_count,
            duplicate_count=self._duplicate_count,
            expired_count=self._expired_count,
            failed_count=self._failed_count,
            active_receipt_ids=active,
            findings=self._findings,
            order_management_request_count=self._order_management_request_count,
            paper_submission_count=self._paper_submission_count,
            broker_order_calls=0,
        )

    def _eligibility_failure(self, request: PaperExecutionRequest, policy: PaperExecutionCoordinatorPolicy) -> PaperExecutionReceipt | None:
        plan = request.execution_plan
        if not policy.enabled:
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.COORDINATOR_LOCKED, "Paper execution coordinator is disabled.", decision=PaperExecutionDecision.LOCKED)
        if self._state is CoordinatorLifecycleState.STOPPED:
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.COORDINATOR_STOPPED, "Paper execution coordinator is stopped.", decision=PaperExecutionDecision.LOCKED)
        if self._state is CoordinatorLifecycleState.LOCKED:
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.COORDINATOR_LOCKED, "Paper execution coordinator is locked.", decision=PaperExecutionDecision.LOCKED)
        if request.instrument != self._instrument or plan.instrument != self._instrument:
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.PLAN_INSTRUMENT_MISMATCH, "Execution plan instrument does not match runtime.", "instrument", plan.instrument, self._instrument)
        if request.instrument not in policy.allowed_instruments:
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.UNSUPPORTED_INSTRUMENT, "Instrument is not allowed.", "instrument", request.instrument)
        if policy.require_paper_routing and plan.routing_target is not ExecutionRoutingTarget.PAPER_TRADING:
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.UNSUPPORTED_ROUTING_TARGET, "Execution plan is not routed to paper trading.", "routing_target", plan.routing_target.value)
        if plan.execution_mode is not ExecutionMode.PAPER:
            observed = plan.execution_mode.value if isinstance(plan.execution_mode, ExecutionMode) else str(plan.execution_mode)
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.UNSUPPORTED_EXECUTION_MODE, "Execution plan is not paper mode.", "execution_mode", observed)
        if policy.require_ready_for_paper and plan.status is not ExecutionPlanStatus.READY_FOR_PAPER:
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.PLAN_NOT_READY_FOR_PAPER, "Execution plan is not ready for paper.", "plan_status", plan.status.value)
        if policy.require_plan_approval and (plan.decision_status is not ExecutionDecisionStatus.APPROVED or plan.primary_reason is not ExecutionReasonCode.APPROVED):
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.PLAN_NOT_APPROVED, "Execution plan is not approved.", "decision_status", plan.decision_status.value)
        if policy.require_plan_not_expired and request.timestamp >= plan.valid_until:
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.PLAN_EXPIRED, "Execution plan is expired.", "valid_until", request.timestamp.isoformat(), plan.valid_until.isoformat(), decision=PaperExecutionDecision.EXPIRED, status=PaperExecutionStatus.EXPIRED)
        if plan.broker_submission_allowed or plan.broker_order_calls != 0:
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.BROKER_SUBMISSION_BLOCKED, "Execution plan cannot permit broker submission.", "broker_order_calls", plan.broker_order_calls, 0)
        if plan.entry_quantity <= 0 or plan.entry_side not in {OrderSide.BUY, OrderSide.SELL}:
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.INVALID_EXECUTION_PLAN, "Execution plan entry configuration is invalid.")
        protective_failure = self._protective_failure(plan)
        if protective_failure is not None:
            return self._rejected_receipt(request, policy, PaperExecutionReasonCode.INVALID_PROTECTIVE_PLAN, protective_failure)
        return None

    def _duplicate_receipt(self, request: PaperExecutionRequest, policy: PaperExecutionCoordinatorPolicy) -> PaperExecutionReceipt | None:
        plan = request.execution_plan
        request_fp = request.fingerprint()
        existing_request_fp = self._request_fingerprints.get(request.request_id)
        if existing_request_fp is not None and existing_request_fp != request_fp:
            return self._store_duplicate_rejection(request, policy, "Request ID already belongs to different content.")
        existing_plan_fp = self._plan_fingerprints.get(plan.execution_plan_id)
        if existing_plan_fp is not None and existing_plan_fp != plan.input_fingerprint:
            return self._store_duplicate_rejection(request, policy, "Execution plan ID already belongs to different content.")
        receipt_id = self._by_plan_id.get(plan.execution_plan_id) or self._by_plan_fingerprint.get(plan.input_fingerprint) or self._by_request_id.get(request.request_id)
        if receipt_id is not None:
            return self._receipts[receipt_id]
        for receipt_id in request.existing_execution_receipt_ids:
            if receipt_id in self._receipts and self._receipts[receipt_id].status in ACTIVE_STATUSES:
                return self._store_duplicate_rejection(request, policy, "Existing receipt blocks duplicate execution.")
        return None

    def _store_duplicate_rejection(self, request, policy, message):
        receipt = self._rejected_receipt(request, policy, PaperExecutionReasonCode.DUPLICATE_EXECUTION, message, decision=PaperExecutionDecision.DUPLICATE)
        self._store_terminal(receipt)
        self._duplicate_count += 1
        self._publish(events.PAPER_EXECUTION_DUPLICATE, receipt)
        self._publish(events.PAPER_EXECUTION_EVALUATED, receipt)
        return receipt

    def _create_entry(self, request: PaperExecutionRequest, policy: PaperExecutionCoordinatorPolicy) -> PaperExecutionReceipt:
        plan = request.execution_plan
        order_request = OrderRequest(
            client_order_id=f"paper-entry:{plan.execution_plan_id}",
            symbol=plan.instrument,
            exchange=self._exchange,
            timeframe=self._timeframe,
            timestamp=request.timestamp,
            side=plan.entry_side,
            order_type=plan.entry_order_type,
            product_type=ProductType.INTRADAY,
            quantity=plan.entry_quantity,
            limit_price=plan.entry_limit_price,
            trigger_price=plan.entry_trigger_price,
        )
        snapshot = OrderSnapshot(
            symbol=plan.instrument,
            timeframe=self._timeframe,
            timestamp=request.timestamp,
            risk=self._risk_state_for_plan(plan, request.timestamp),
            request=order_request,
        )
        order = self._order_engine.create(snapshot)
        self._order_management_request_count += 1
        if not hasattr(self._paper_engine, "submit_managed_order"):
            raise ExpectedCoordinationError(PaperExecutionReasonCode.PAPER_SUBMISSION_FAILED, "Paper trading boundary cannot submit managed orders.")
        try:
            paper_submission_id = self._paper_engine.submit_managed_order(order, execution_plan=plan, purpose=CoordinatedOrderPurpose.ENTRY.value)
        except Exception as exc:
            failed_receipt = self._receipt(
                request,
                policy,
                entry_order=_order_reference(order, CoordinatedOrderPurpose.ENTRY),
                paper_submission_id=None,
                status=PaperExecutionStatus.FAILED,
                decision=PaperExecutionDecision.INVALID,
                reason=PaperExecutionReasonCode.PAPER_SUBMISSION_FAILED,
                findings=(self._finding(request.timestamp, PaperExecutionSeverity.ERROR, PaperExecutionReasonCode.PAPER_SUBMISSION_FAILED, _safe_message(exc)),),
                order_delta=1,
                paper_delta=0,
            )
            self._request_id_by_receipt[failed_receipt.receipt_id] = request.request_id
            self._latest_plan_by_receipt[failed_receipt.receipt_id] = plan
            return failed_receipt
        self._paper_submission_count += 1
        receipt = self._receipt(
            request,
            policy,
            entry_order=_order_reference(order, CoordinatedOrderPurpose.ENTRY),
            paper_submission_id=paper_submission_id,
            status=PaperExecutionStatus.ENTRY_SUBMITTED,
            decision=PaperExecutionDecision.APPROVED,
            reason=PaperExecutionReasonCode.APPROVED,
            order_delta=1,
            paper_delta=1,
        )
        self._request_id_by_receipt[receipt.receipt_id] = request.request_id
        self._latest_plan_by_receipt[receipt.receipt_id] = plan
        return receipt

    def _create_protective_orders(self, receipt: PaperExecutionReceipt, entry: OrderState, timestamp: datetime) -> PaperExecutionReceipt:
        plan = self._plan_for_receipt(receipt)
        if plan is None or entry.filled_quantity <= 0:
            return receipt
        if entry.filled_quantity > plan.entry_quantity:
            finding = self._finding(timestamp, PaperExecutionSeverity.ERROR, PaperExecutionReasonCode.INCONSISTENT_ORDER_STATE, "Filled quantity exceeds approved plan quantity.", "filled_quantity", entry.filled_quantity, plan.entry_quantity)
            return self._transition(receipt, timestamp, PaperExecutionStatus.FAILED, PaperExecutionDecision.INVALID, PaperExecutionReasonCode.INCONSISTENT_ORDER_STATE, finding)
        stop_ref = receipt.stop_order
        target_ref = receipt.target_order
        order_delta = 0
        paper_delta = 0
        for protective in (plan.stop_plan, plan.target_plan):
            if protective is None:
                continue
            purpose = CoordinatedOrderPurpose.STOP_LOSS if protective.purpose is ProtectiveOrderPurpose.STOP_LOSS else CoordinatedOrderPurpose.TARGET
            if purpose is CoordinatedOrderPurpose.STOP_LOSS and stop_ref is not None:
                continue
            if purpose is CoordinatedOrderPurpose.TARGET and target_ref is not None:
                continue
            order = self._create_protective_order(plan, protective, purpose, entry.filled_quantity, timestamp)
            self._order_management_request_count += 1
            order_delta += 1
            self._paper_engine.submit_managed_order(order, execution_plan=plan, purpose=purpose.value)
            self._paper_submission_count += 1
            paper_delta += 1
            ref = _order_reference(order, purpose, reduce_only=True)
            if purpose is CoordinatedOrderPurpose.STOP_LOSS:
                stop_ref = ref
            else:
                target_ref = ref
        status = PaperExecutionStatus.PROTECTIVE_ORDERS_CREATED if stop_ref is not None or target_ref is not None else PaperExecutionStatus.ENTRY_FILLED
        return replace(
            receipt,
            updated_at=timestamp,
            status=status,
            stop_order=stop_ref,
            target_order=target_ref,
            order_management_request_count=receipt.order_management_request_count + order_delta,
            paper_submission_count=receipt.paper_submission_count + paper_delta,
        )

    def _create_protective_order(self, plan: TradeExecutionPlan, protective: ProtectiveOrderPlan, purpose: CoordinatedOrderPurpose, quantity: int, timestamp: datetime) -> OrderState:
        if protective.quantity != plan.entry_quantity or quantity <= 0 or not protective.reduce_only:
            raise ExpectedCoordinationError(PaperExecutionReasonCode.INVALID_PROTECTIVE_PLAN, "Protective plan is inconsistent.")
        order_type = protective.order_type
        limit = protective.limit_price
        trigger = protective.trigger_price
        if purpose is CoordinatedOrderPurpose.STOP_LOSS and order_type is OrderType.STOP_LIMIT and trigger is not None:
            order_type = OrderType.STOP_MARKET
            limit = None
        request = OrderRequest(
            client_order_id=f"paper-{purpose.value}:{plan.execution_plan_id}",
            symbol=plan.instrument,
            exchange=self._exchange,
            timeframe=self._timeframe,
            timestamp=timestamp,
            side=protective.side,
            order_type=order_type,
            product_type=ProductType.INTRADAY,
            quantity=quantity,
            limit_price=limit,
            trigger_price=trigger,
        )
        risk = self._risk_state_for_order(plan, protective.side, limit or trigger or plan.market_reference_price, timestamp)
        snapshot = OrderSnapshot(plan.instrument, self._timeframe, timestamp, risk, request)
        return self._order_engine.create(snapshot)

    def _receipt(self, request, policy, *, entry_order, paper_submission_id, status, decision, reason, findings=(), order_delta=0, paper_delta=0):
        plan = request.execution_plan
        return PaperExecutionReceipt(
            receipt_id=receipt_identity(request, policy),
            created_at=request.timestamp,
            updated_at=request.timestamp,
            instrument=request.instrument,
            execution_plan_id=plan.execution_plan_id,
            execution_plan_fingerprint=plan.input_fingerprint,
            request_fingerprint=request.fingerprint(),
            entry_order=entry_order,
            stop_order=None,
            target_order=None,
            paper_submission_id=paper_submission_id,
            status=status,
            decision=decision,
            primary_reason=reason,
            findings=tuple(findings),
            entry_filled_quantity=0,
            remaining_quantity=plan.entry_quantity,
            broker_submission_allowed=False,
            broker_order_calls=0,
            order_management_request_count=order_delta,
            paper_submission_count=paper_delta,
            risk_decision_id=plan.risk_decision_id,
            signal_id=plan.signal_id,
            strategy_id=plan.strategy_id,
            client_request_id=plan.client_request_id,
            correlation_id=request.correlation_id,
            session_id=request.session_id,
        )

    def _rejected_receipt(self, request, policy, reason, message, field_name=None, observed=None, expected=None, *, decision=PaperExecutionDecision.REJECTED, status=PaperExecutionStatus.REJECTED, severity=PaperExecutionSeverity.ERROR):
        finding = self._finding(request.timestamp, severity, reason, message, field_name, observed, expected)
        receipt = self._receipt(
            request,
            policy,
            entry_order=None,
            paper_submission_id=None,
            status=status,
            decision=decision,
            reason=reason,
            findings=(finding,),
        )
        return receipt

    def _transition(self, receipt, timestamp, status, decision, reason, finding):
        return replace(receipt, updated_at=timestamp, status=status, decision=decision, primary_reason=reason, findings=tuple((receipt.findings + (finding,))[-self._policy.maximum_findings:]))

    def _store_active(self, receipt: PaperExecutionReceipt) -> None:
        self._store(receipt)
        if receipt.entry_order is not None:
            self._by_order_id[receipt.entry_order.order_id] = receipt.receipt_id
        if receipt.stop_order is not None:
            self._by_order_id[receipt.stop_order.order_id] = receipt.receipt_id
        if receipt.target_order is not None:
            self._by_order_id[receipt.target_order.order_id] = receipt.receipt_id
        self._data = receipt

    def _store_terminal(self, receipt: PaperExecutionReceipt) -> None:
        self._store(receipt)
        self._findings = tuple((self._findings + receipt.findings)[-self._policy.maximum_findings:])
        if receipt.status is PaperExecutionStatus.FAILED:
            self._failed_count += 1
        elif receipt.decision is PaperExecutionDecision.EXPIRED:
            self._expired_count += 1
        elif receipt.decision in {PaperExecutionDecision.REJECTED, PaperExecutionDecision.INVALID, PaperExecutionDecision.LOCKED} and receipt.status is not PaperExecutionStatus.FAILED:
            self._rejected_count += 1
        self._data = receipt

    def _store(self, receipt: PaperExecutionReceipt) -> None:
        plan_id = receipt.execution_plan_id
        self._receipts[receipt.receipt_id] = receipt
        if receipt.entry_order is not None:
            self._by_plan_id[plan_id] = receipt.receipt_id
            self._plan_fingerprints[plan_id] = receipt.execution_plan_fingerprint
            self._by_plan_fingerprint[receipt.execution_plan_fingerprint] = receipt.receipt_id
            request_id = self._request_id_by_receipt.get(receipt.receipt_id)
            if request_id is not None:
                self._by_request_id[request_id] = receipt.receipt_id
                self._request_fingerprints[request_id] = receipt.request_fingerprint
        self._last_receipt = receipt

    def _publish_terminal(self, receipt):
        if receipt.status is PaperExecutionStatus.EXPIRED:
            self._publish(events.PAPER_EXECUTION_REJECTED, receipt)
        elif receipt.decision is PaperExecutionDecision.DUPLICATE:
            self._publish(events.PAPER_EXECUTION_DUPLICATE, receipt)
        else:
            self._publish(events.PAPER_EXECUTION_REJECTED, receipt)
        self._publish(events.PAPER_EXECUTION_EVALUATED, receipt)
        self._publish(events.PAPER_EXECUTION_COORDINATOR_STATE_UPDATED, self.snapshot())

    def _finding(self, timestamp, severity, reason, message, field_name=None, observed=None, expected=None):
        return PaperExecutionFinding(
            finding_id=finding_identity(timestamp, reason, message, field_name, observed, expected),
            timestamp=timestamp,
            severity=severity,
            reason_code=reason,
            message=message,
            field_name=field_name,
            observed_value=None if observed is None else str(observed),
            expected_value=None if expected is None else str(expected),
        )

    def _protective_failure(self, plan: TradeExecutionPlan) -> str | None:
        for protective in (plan.stop_plan, plan.target_plan):
            if protective is None:
                continue
            if protective.quantity != plan.entry_quantity:
                return "Protective quantity must match entry quantity."
            if not protective.reduce_only:
                return "Protective order must be reduce_only."
            if protective.side is plan.entry_side:
                return "Protective side must oppose entry side."
        return None

    def _risk_state_for_plan(self, plan: TradeExecutionPlan, timestamp: datetime) -> RiskDecisionState:
        stop = plan.stop_plan.trigger_price if plan.stop_plan is not None and plan.stop_plan.trigger_price is not None else plan.market_reference_price
        target = plan.target_plan.limit_price if plan.target_plan is not None and plan.target_plan.limit_price is not None else plan.market_reference_price
        entry = plan.entry_trigger_price if plan.entry_order_type is OrderType.STOP_LIMIT and plan.entry_trigger_price is not None else plan.entry_limit_price or plan.market_reference_price
        return self._risk_state(plan, plan.direction, entry, stop, target, timestamp)

    def _risk_state_for_order(self, plan: TradeExecutionPlan, side: OrderSide, price: float, timestamp: datetime) -> RiskDecisionState:
        from engines.strategy.enums import TradeDirection

        direction = TradeDirection.BULLISH if side is OrderSide.BUY else TradeDirection.BEARISH
        if direction is TradeDirection.BULLISH:
            stop = max(0.05, price - 0.05)
            target = price + 0.05
        else:
            stop = price + 0.05
            target = max(0.05, price - 0.05)
        return self._risk_state(plan, direction, price, stop, target, timestamp)

    def _risk_state(self, plan: TradeExecutionPlan, direction, entry_price: float, stop: float, target: float, timestamp: datetime) -> RiskDecisionState:
        return RiskDecisionState(
            symbol=plan.instrument,
            timeframe=self._timeframe,
            timestamp=timestamp,
            decision=RiskDecision.APPROVED,
            risk_tier=RiskTier.STANDARD,
            rejection_reason=RiskRejectionReason.NONE,
            reduction_reason=RiskReductionReason.NONE,
            direction=direction,
            account_equity=0.0,
            realized_pnl_today=0.0,
            daily_loss_limit_amount=0.0,
            remaining_daily_loss_capacity=0.0,
            applied_risk_percent=0.0,
            risk_budget=0.0,
            entry_price=entry_price,
            stop_price=stop,
            target_price=target,
            stop_distance=abs(entry_price - stop),
            target_distance=abs(target - entry_price),
            reward_risk_ratio=1.0,
            lot_size=plan.entry_quantity,
            requested_lots=1,
            maximum_permitted_lots=1,
            approved_lots=1,
            approved_quantity=plan.entry_quantity,
            estimated_risk_amount=0.0,
            estimated_reward_amount=0.0,
            rationale=("paper execution coordinator",),
            plan_id=plan.risk_decision_id,
            plan_status="READY",
            valid_until=plan.valid_until,
            trade_plan_ready=True,
        )

    def _plan_for_receipt(self, receipt: PaperExecutionReceipt) -> TradeExecutionPlan | None:
        return self._latest_plan_by_receipt.get(receipt.receipt_id)

    def _publish(self, event_name: str, payload) -> None:
        self._event_bus.publish(event_name, payload)


class ExpectedCoordinationError(ValueError):
    def __init__(self, reason, message, field_name=None, observed=None, expected=None):
        super().__init__(message)
        self.reason = reason
        self.field_name = field_name
        self.observed = observed
        self.expected = expected


def _order_reference(order: OrderState, purpose: CoordinatedOrderPurpose, *, reduce_only: bool = False) -> CoordinatedOrderReference:
    return CoordinatedOrderReference(
        order_id=order.client_order_id,
        purpose=purpose,
        side=order.side,
        order_type=order.order_type,
        quantity=order.quantity,
        limit_price=order.limit_price,
        trigger_price=order.trigger_price,
        status=order.status,
        created_at=order.created_at,
        reduce_only=reduce_only,
    )
def _instrument(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("instrument must be non-empty text")
    normalized = value.strip().upper()
    if normalized not in {"NIFTY", "BANKNIFTY", "SENSEX"}:
        raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
    return normalized


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _safe_message(exc: Exception) -> str:
    return (str(exc).strip() or exc.__class__.__name__)[:500]
