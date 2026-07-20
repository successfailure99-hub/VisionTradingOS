"""
Synchronous read-only Execution Reconciliation Engine V1.
"""

from __future__ import annotations

from datetime import datetime

from core import events
from core.base_engine import BaseEngine
from engines.order_management.enums import OrderSide, OrderStatus
from engines.order_management.models import OrderState
from engines.order_management.order_management_engine import OrderManagementEngine
from engines.paper_execution_coordinator.enums import CoordinatedOrderPurpose, PaperExecutionStatus
from engines.paper_execution_coordinator.models import CoordinatedOrderReference, PaperExecutionReceipt
from engines.paper_trading.engine import PaperTradingEngine
from engines.paper_trading.enums import ManagedPaperSubmissionStatus
from engines.paper_trading.models import ManagedPaperSubmission
from engines.position.enums import PositionSide, PositionStatus
from engines.position.models import PositionState
from engines.position.position_engine import PositionEngine
from engines.trade_execution_policy.models import ProtectiveOrderPlan, TradeExecutionPlan
from engines.execution_reconciliation.enums import (
    ReconciliationBoundary,
    ReconciliationLifecycleState,
    ReconciliationReasonCode,
    ReconciliationSeverity,
    ReconciliationStatus,
)
from engines.execution_reconciliation.models import (
    ExecutionReconciliationPolicy,
    ExecutionReconciliationReport,
    ExecutionReconciliationRequest,
    ExecutionReconciliationSnapshot,
    ReconciledOrderState,
    ReconciliationFinding,
    finding_identity,
    model_fingerprint,
    report_identity,
)


ACTIVE_ORDER_STATUSES = {OrderStatus.PENDING_SUBMISSION, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}
TERMINAL_ORDER_STATUSES = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}
TERMINAL_RECEIPT_STATUSES = {
    PaperExecutionStatus.COMPLETED,
    PaperExecutionStatus.CANCELLED,
    PaperExecutionStatus.REJECTED,
    PaperExecutionStatus.EXPIRED,
    PaperExecutionStatus.FAILED,
}
ACTIVE_RECEIPT_STATUSES = {
    PaperExecutionStatus.ENTRY_SUBMITTED,
    PaperExecutionStatus.ENTRY_PARTIALLY_FILLED,
    PaperExecutionStatus.ENTRY_FILLED,
    PaperExecutionStatus.PROTECTIVE_ORDERS_CREATED,
    PaperExecutionStatus.ACTIVE,
}
TERMINAL_MANAGED_STATUSES = {
    ManagedPaperSubmissionStatus.FILLED,
    ManagedPaperSubmissionStatus.CANCELLED,
    ManagedPaperSubmissionStatus.REJECTED,
}
EXPECTED_MANAGED_STATUS = {
    OrderStatus.PENDING_SUBMISSION: ManagedPaperSubmissionStatus.SUBMITTED,
    OrderStatus.SUBMITTED: ManagedPaperSubmissionStatus.SUBMITTED,
    OrderStatus.PARTIALLY_FILLED: ManagedPaperSubmissionStatus.PARTIALLY_FILLED,
    OrderStatus.FILLED: ManagedPaperSubmissionStatus.FILLED,
    OrderStatus.CANCELLED: ManagedPaperSubmissionStatus.CANCELLED,
    OrderStatus.REJECTED: ManagedPaperSubmissionStatus.REJECTED,
}
INCOMPLETE_REASONS = {
    ReconciliationReasonCode.RECEIPT_NOT_FOUND,
    ReconciliationReasonCode.ORDER_NOT_FOUND,
    ReconciliationReasonCode.ENTRY_ORDER_NOT_FOUND,
    ReconciliationReasonCode.STOP_ORDER_NOT_FOUND,
    ReconciliationReasonCode.TARGET_ORDER_NOT_FOUND,
    ReconciliationReasonCode.MANAGED_SUBMISSION_NOT_FOUND,
    ReconciliationReasonCode.POSITION_NOT_FOUND,
    ReconciliationReasonCode.MISSING_STOP_PROTECTION,
    ReconciliationReasonCode.MISSING_TARGET_PROTECTION,
    ReconciliationReasonCode.FILLED_ENTRY_WITHOUT_POSITION,
}
SEVERITY_ORDER = {
    ReconciliationSeverity.CRITICAL: 0,
    ReconciliationSeverity.ERROR: 1,
    ReconciliationSeverity.WARNING: 2,
    ReconciliationSeverity.INFO: 3,
}


class ExecutionReconciliationEngine(BaseEngine):
    """
    Read-only cross-boundary reconciliation for one runtime instrument.

    The engine reads Order Management, managed Paper Trading submissions and
    Position state, compares them against a paper-execution receipt and its
    source execution plan, then publishes immutable reports. It never mutates
    orders, submissions, positions, receipts, or broker state.
    """

    def __init__(
        self,
        event_bus,
        *,
        instrument: str,
        timeframe: str,
        order_management_engine: OrderManagementEngine,
        paper_trading_engine: PaperTradingEngine,
        position_engine: PositionEngine,
        paper_execution_coordinator=None,
        execution_policy_engine=None,
        policy: ExecutionReconciliationPolicy | None = None,
    ):
        super().__init__(event_bus)
        if not isinstance(order_management_engine, OrderManagementEngine):
            raise TypeError("order_management_engine must be OrderManagementEngine")
        if not isinstance(paper_trading_engine, PaperTradingEngine):
            raise TypeError("paper_trading_engine must be PaperTradingEngine")
        if not isinstance(position_engine, PositionEngine):
            raise TypeError("position_engine must be PositionEngine")
        self._instrument = _instrument(instrument)
        self._timeframe = _text(timeframe, "timeframe")
        self._order_engine = order_management_engine
        self._paper_engine = paper_trading_engine
        self._position_engine = position_engine
        self._coordinator = paper_execution_coordinator
        self._execution_policy_engine = execution_policy_engine
        self._policy = policy or ExecutionReconciliationPolicy()
        if not isinstance(self._policy, ExecutionReconciliationPolicy):
            raise TypeError("policy must be ExecutionReconciliationPolicy")
        self._state = ReconciliationLifecycleState.CREATED
        self._reports: dict[str, ExecutionReconciliationReport] = {}
        self._request_fingerprints: dict[str, str] = {}
        self._request_reports: dict[str, str] = {}
        self._input_reports: dict[str, str] = {}
        self._last_report: ExecutionReconciliationReport | None = None
        self._findings: tuple[ReconciliationFinding, ...] = ()
        self._reconciliation_count = 0
        self._consistent_count = 0
        self._warning_count = 0
        self._inconsistent_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._order_reads = 0
        self._paper_reads = 0
        self._position_reads = 0

    def start(self) -> ExecutionReconciliationSnapshot:
        if self._state is not ReconciliationLifecycleState.STOPPED:
            self._state = ReconciliationLifecycleState.READY
        snapshot = self.snapshot()
        self._publish(events.EXECUTION_RECONCILIATION_STATE_UPDATED, snapshot)
        return snapshot

    def stop(self) -> ExecutionReconciliationSnapshot:
        self._state = ReconciliationLifecycleState.STOPPED
        snapshot = self.snapshot()
        self._publish(events.EXECUTION_RECONCILIATION_STATE_UPDATED, snapshot)
        return snapshot

    def reset_session(self) -> ExecutionReconciliationSnapshot:
        self._reports.clear()
        self._request_fingerprints.clear()
        self._request_reports.clear()
        self._input_reports.clear()
        self._last_report = None
        self._findings = ()
        self._state = ReconciliationLifecycleState.READY
        snapshot = self.snapshot()
        self._publish(events.EXECUTION_RECONCILIATION_STATE_UPDATED, snapshot)
        return snapshot

    def reconcile_receipt(self, receipt_id: str, *, timestamp: datetime) -> ExecutionReconciliationReport:
        _aware(timestamp, "timestamp")
        rid = _text(receipt_id, "receipt_id")
        receipt = self._lookup_receipt(rid)
        if receipt is None:
            return self._minimal_report(
                timestamp,
                instrument=self._instrument,
                plan_id="-",
                plan_fingerprint="-",
                receipt_id=rid,
                receipt_status="-",
                request_fingerprint=f"missing:{rid}",
                reason=ReconciliationReasonCode.RECEIPT_NOT_FOUND,
                message="Paper execution receipt was not found.",
                boundary=ReconciliationBoundary.COORDINATOR_RECEIPT,
                status=ReconciliationStatus.INCOMPLETE,
            )
        plan = self._lookup_plan(receipt.execution_plan_id)
        if plan is None:
            return self._minimal_report(
                timestamp,
                instrument=receipt.instrument,
                plan_id=receipt.execution_plan_id,
                plan_fingerprint=receipt.execution_plan_fingerprint,
                receipt_id=receipt.receipt_id,
                receipt_status=receipt.status.value,
                request_fingerprint=f"missing-plan:{receipt.receipt_id}",
                reason=ReconciliationReasonCode.INVALID_EXECUTION_PLAN,
                message="Execution plan was not available for receipt reconciliation.",
                boundary=ReconciliationBoundary.EXECUTION_PLAN,
                status=ReconciliationStatus.INCOMPLETE,
            )
        request = ExecutionReconciliationRequest(
            request_id=f"reconcile:{receipt.receipt_id}",
            timestamp=timestamp,
            instrument=receipt.instrument,
            execution_plan=plan,
            execution_receipt=receipt,
            correlation_id=receipt.correlation_id,
            session_id=receipt.session_id,
        )
        return self.reconcile(request)

    def reconcile(
        self,
        request: ExecutionReconciliationRequest,
        policy: ExecutionReconciliationPolicy | None = None,
    ) -> ExecutionReconciliationReport:
        if not isinstance(request, ExecutionReconciliationRequest):
            raise TypeError("request must be ExecutionReconciliationRequest")
        active_policy = policy or self._policy
        if not isinstance(active_policy, ExecutionReconciliationPolicy):
            raise TypeError("policy must be ExecutionReconciliationPolicy")
        if self._state is ReconciliationLifecycleState.STOPPED:
            return self._blocked_report(request, ReconciliationReasonCode.ENGINE_STOPPED, "Execution reconciliation engine is stopped.")
        if self._state is ReconciliationLifecycleState.LOCKED or not active_policy.enabled:
            return self._blocked_report(request, ReconciliationReasonCode.ENGINE_LOCKED, "Execution reconciliation engine is locked.")
        if self._state is ReconciliationLifecycleState.CREATED:
            self._state = ReconciliationLifecycleState.READY

        request_fp = request.fingerprint()
        existing_fp = self._request_fingerprints.get(request.request_id)
        if existing_fp is not None and existing_fp != request_fp:
            return self._duplicate_conflict_report(request, request_fp, existing_fp)
        existing_report_id = self._request_reports.get(request.request_id)
        if existing_report_id is not None:
            return self._reports[existing_report_id]

        self._publish(events.EXECUTION_RECONCILIATION_STARTED, request)
        try:
            report = self._reconcile(request, active_policy, request_fp)
        except Exception as exc:
            self._state = ReconciliationLifecycleState.FAILED
            report = self._failed_report(request, request_fp, exc)

        self._store_report(request, report, request_fp)
        self._publish_report(report)
        return report

    def snapshot(self) -> ExecutionReconciliationSnapshot:
        return ExecutionReconciliationSnapshot(
            enabled=self._policy.enabled,
            lifecycle_state=self._state,
            last_report=self._last_report,
            reconciliation_count=self._reconciliation_count,
            consistent_count=self._consistent_count,
            warning_count=self._warning_count,
            inconsistent_count=self._inconsistent_count,
            invalid_count=self._invalid_count,
            failed_count=self._failed_count,
            active_report_ids=tuple(sorted(self._reports)),
            findings=self._findings[-self._policy.maximum_findings :],
            order_management_read_count=self._order_reads,
            paper_trading_read_count=self._paper_reads,
            position_read_count=self._position_reads,
            broker_order_calls=0,
            mutation_calls=0,
        )

    def _reconcile(self, request: ExecutionReconciliationRequest, policy: ExecutionReconciliationPolicy, request_fp: str) -> ExecutionReconciliationReport:
        plan = request.execution_plan
        receipt = request.execution_receipt
        findings: list[ReconciliationFinding] = []
        checked = {
            ReconciliationBoundary.EXECUTION_PLAN,
            ReconciliationBoundary.COORDINATOR_RECEIPT,
            ReconciliationBoundary.ORDER_MANAGEMENT,
            ReconciliationBoundary.PAPER_TRADING,
            ReconciliationBoundary.POSITION,
            ReconciliationBoundary.CROSS_BOUNDARY,
        }

        if request.instrument != self._instrument:
            findings.append(self._finding(request.timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.INSTRUMENT_MISMATCH, "Request instrument does not match runtime.", ReconciliationBoundary.CROSS_BOUNDARY, "instrument", request.instrument, self._instrument))
        if request.instrument not in policy.allowed_instruments:
            findings.append(self._finding(request.timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.INVALID_REQUEST, "Instrument is not allowed for reconciliation.", ReconciliationBoundary.CROSS_BOUNDARY, "instrument", request.instrument, ",".join(policy.allowed_instruments)))
        if plan.instrument != self._instrument:
            findings.append(self._finding(request.timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.INSTRUMENT_MISMATCH, "Execution plan instrument does not match runtime.", ReconciliationBoundary.EXECUTION_PLAN, "instrument", plan.instrument, self._instrument))
        if receipt.instrument != self._instrument:
            findings.append(self._finding(request.timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.INSTRUMENT_MISMATCH, "Receipt instrument does not match runtime.", ReconciliationBoundary.COORDINATOR_RECEIPT, "instrument", receipt.instrument, self._instrument))
        if receipt.execution_plan_id != plan.execution_plan_id:
            findings.append(self._finding(request.timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.EXECUTION_PLAN_ID_MISMATCH, "Receipt references a different execution plan.", ReconciliationBoundary.CROSS_BOUNDARY, "execution_plan_id", receipt.execution_plan_id, plan.execution_plan_id))
        if receipt.execution_plan_fingerprint != plan.input_fingerprint:
            findings.append(self._finding(request.timestamp, ReconciliationSeverity.CRITICAL, ReconciliationReasonCode.EXECUTION_PLAN_FINGERPRINT_MISMATCH, "Receipt execution-plan fingerprint differs from the plan.", ReconciliationBoundary.CROSS_BOUNDARY, "execution_plan_fingerprint", receipt.execution_plan_fingerprint, plan.input_fingerprint))
        if receipt.risk_decision_id is not None and receipt.risk_decision_id != plan.risk_decision_id:
            findings.append(self._finding(request.timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.EXECUTION_PLAN_ID_MISMATCH, "Receipt risk decision differs from the execution plan.", ReconciliationBoundary.CROSS_BOUNDARY, "risk_decision_id", receipt.risk_decision_id, plan.risk_decision_id))
        if receipt.entry_filled_quantity > plan.entry_quantity:
            findings.append(self._finding(request.timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.FILLED_QUANTITY_MISMATCH, "Receipt entry filled quantity exceeds plan quantity.", ReconciliationBoundary.COORDINATOR_RECEIPT, "entry_filled_quantity", receipt.entry_filled_quantity, plan.entry_quantity))
        if receipt.broker_submission_allowed or receipt.broker_order_calls != 0 or plan.broker_submission_allowed or plan.broker_order_calls != 0:
            findings.append(self._finding(request.timestamp, ReconciliationSeverity.CRITICAL, ReconciliationReasonCode.INVALID_RECEIPT, "Broker submission counters must remain blocked.", ReconciliationBoundary.CROSS_BOUNDARY, "broker_order_calls", receipt.broker_order_calls, 0))

        refs = {
            "entry": receipt.entry_order,
            "stop_loss": receipt.stop_order,
            "target": receipt.target_order,
        }
        self._detect_duplicate_references(request.timestamp, refs, receipt, findings)

        entry_order = request.entry_order if request.entry_order is not None else self._read_order(receipt.entry_order.order_id if receipt.entry_order else None)
        stop_order = request.stop_order if request.stop_order is not None else self._read_order(receipt.stop_order.order_id if receipt.stop_order else None)
        target_order = request.target_order if request.target_order is not None else self._read_order(receipt.target_order.order_id if receipt.target_order else None)
        entry_submission = request.entry_managed_submission if request.entry_managed_submission is not None else self._read_submission(receipt.paper_submission_id or (receipt.entry_order.order_id if receipt.entry_order else None))
        stop_submission = request.stop_managed_submission if request.stop_managed_submission is not None else self._read_submission(receipt.stop_paper_submission_id or (receipt.stop_order.order_id if receipt.stop_order else None))
        target_submission = request.target_managed_submission if request.target_managed_submission is not None else self._read_submission(receipt.target_paper_submission_id or (receipt.target_order.order_id if receipt.target_order else None))
        position = request.position if request.position is not None else self._read_position()

        self._check_order("entry", receipt.entry_order, entry_order, entry_submission, plan, findings, request.timestamp, policy)
        self._check_order("stop_loss", receipt.stop_order, stop_order, stop_submission, plan.stop_plan, findings, request.timestamp, policy, plan=plan)
        self._check_order("target", receipt.target_order, target_order, target_submission, plan.target_plan, findings, request.timestamp, policy, plan=plan)
        self._check_protection_lifecycle(request.timestamp, plan, receipt, entry_order, stop_order, target_order, findings, policy)
        self._check_receipt_status(request.timestamp, receipt, entry_order, stop_order, target_order, position, findings, policy)
        self._check_position(request.timestamp, plan, receipt, entry_order, position, findings, policy)
        self._check_orphans(request.timestamp, plan, receipt, refs, findings)

        ordered_findings = _sort_findings(findings)[: policy.maximum_findings]
        input_fp = model_fingerprint(
            {
                "plan": plan,
                "receipt": receipt,
                "entry_order": entry_order,
                "stop_order": stop_order,
                "target_order": target_order,
                "entry_submission": entry_submission,
                "stop_submission": stop_submission,
                "target_submission": target_submission,
                "position": position,
                "policy": policy,
            }
        )
        existing = self._input_reports.get(input_fp)
        if existing is not None:
            return self._reports[existing]
        status = _status_for(ordered_findings)
        primary = _primary_reason(ordered_findings)
        report_id = report_identity(request, input_fp)
        return ExecutionReconciliationReport(
            report_id=report_id,
            created_at=request.timestamp,
            instrument=request.instrument,
            execution_plan_id=plan.execution_plan_id,
            execution_plan_fingerprint=plan.input_fingerprint,
            receipt_id=receipt.receipt_id,
            receipt_status=receipt.status.value,
            reconciliation_status=status,
            primary_reason=primary,
            findings=tuple(ordered_findings),
            entry=_normalized_state("entry", receipt.entry_order, entry_order, entry_submission),
            stop=_normalized_state("stop_loss", receipt.stop_order, stop_order, stop_submission),
            target=_normalized_state("target", receipt.target_order, target_order, target_submission),
            position_id=_position_id(position),
            position_status=position.status if position is not None else None,
            position_quantity=position.absolute_quantity if position is not None else None,
            checked_boundaries=tuple(sorted(checked, key=lambda item: item.value)),
            request_fingerprint=request_fp,
            input_fingerprint=input_fp,
            order_management_read_count=self._order_reads,
            paper_trading_read_count=self._paper_reads,
            position_read_count=self._position_reads,
            broker_order_calls=0,
            mutation_calls=0,
            risk_decision_id=plan.risk_decision_id,
            signal_id=plan.signal_id,
            strategy_id=plan.strategy_id,
            client_request_id=plan.client_request_id,
            correlation_id=request.correlation_id,
            session_id=request.session_id,
        )

    def _check_order(self, purpose, reference, order, submission, expected, findings, timestamp, policy, *, plan=None) -> None:
        plan_for_submission = plan if plan is not None else expected if isinstance(expected, TradeExecutionPlan) else None
        if reference is None and expected is None:
            return
        if reference is None:
            if purpose == "entry" and policy.require_entry_order:
                findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ENTRY_ORDER_NOT_FOUND, "Receipt does not reference an entry order.", ReconciliationBoundary.COORDINATOR_RECEIPT, related=purpose))
            return
        if order is None:
            reason = _missing_order_reason(purpose)
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, reason, f"{purpose} order referenced by receipt was not found.", ReconciliationBoundary.ORDER_MANAGEMENT, "order_id", None, reference.order_id, reference.order_id))
            return
        if not isinstance(order, OrderState):
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.INVALID_ORDER_STATE, "Order state has an invalid type.", ReconciliationBoundary.ORDER_MANAGEMENT, related=reference.order_id))
            return
        expected_instrument = getattr(expected, "instrument", None) or getattr(plan, "instrument", None)
        if order.client_order_id != reference.order_id:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORDER_NOT_FOUND, "Order identity differs from receipt reference.", ReconciliationBoundary.ORDER_MANAGEMENT, "order_id", order.client_order_id, reference.order_id, reference.order_id))
        if order.side is not reference.side:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORDER_SIDE_MISMATCH, "Receipt order side differs from Order Management.", ReconciliationBoundary.COORDINATOR_RECEIPT, "side", reference.side.value, order.side.value, reference.order_id))
        if order.order_type is not reference.order_type:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORDER_TYPE_MISMATCH, "Receipt order type differs from Order Management.", ReconciliationBoundary.COORDINATOR_RECEIPT, "order_type", reference.order_type.value, order.order_type.value, reference.order_id))
        if order.quantity != reference.quantity:
            reason = ReconciliationReasonCode.ORDER_QUANTITY_MISMATCH if purpose == "entry" else ReconciliationReasonCode.PROTECTIVE_QUANTITY_MISMATCH
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, reason, "Receipt order quantity differs from Order Management.", ReconciliationBoundary.COORDINATOR_RECEIPT, "quantity", reference.quantity, order.quantity, reference.order_id))
        if order.limit_price != reference.limit_price:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORDER_LIMIT_PRICE_MISMATCH, "Receipt order limit price differs from Order Management.", ReconciliationBoundary.COORDINATOR_RECEIPT, "limit_price", reference.limit_price, order.limit_price, reference.order_id))
        if order.trigger_price != reference.trigger_price:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORDER_TRIGGER_PRICE_MISMATCH, "Receipt order trigger price differs from Order Management.", ReconciliationBoundary.COORDINATOR_RECEIPT, "trigger_price", reference.trigger_price, order.trigger_price, reference.order_id))
        if expected_instrument is not None and order.symbol != expected_instrument:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.INSTRUMENT_MISMATCH, "Order instrument differs from expected instrument.", ReconciliationBoundary.ORDER_MANAGEMENT, "instrument", order.symbol, expected_instrument, order.client_order_id))
        expected_side = getattr(expected, "entry_side", None) or getattr(expected, "side", None)
        if expected_side is not None and order.side is not expected_side:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORDER_SIDE_MISMATCH, "Order side differs from expected side.", ReconciliationBoundary.ORDER_MANAGEMENT, "side", order.side.value, expected_side.value, order.client_order_id))
        expected_type = getattr(expected, "entry_order_type", None) or getattr(expected, "order_type", None)
        if expected_type is not None and order.order_type is not expected_type:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORDER_TYPE_MISMATCH, "Order type differs from expected type.", ReconciliationBoundary.ORDER_MANAGEMENT, "order_type", order.order_type.value, expected_type.value, order.client_order_id))
        expected_quantity = getattr(expected, "entry_quantity", None) or getattr(expected, "quantity", None)
        if expected_quantity is not None and order.quantity != expected_quantity:
            reason = ReconciliationReasonCode.ORDER_QUANTITY_MISMATCH if purpose == "entry" else ReconciliationReasonCode.PROTECTIVE_QUANTITY_MISMATCH
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, reason, "Order quantity differs from expected quantity.", ReconciliationBoundary.ORDER_MANAGEMENT, "quantity", order.quantity, expected_quantity, order.client_order_id))
        expected_limit = getattr(expected, "entry_limit_price", None) if hasattr(expected, "entry_limit_price") else getattr(expected, "limit_price", None)
        if order.limit_price != expected_limit:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORDER_LIMIT_PRICE_MISMATCH, "Order limit price differs from expected price.", ReconciliationBoundary.ORDER_MANAGEMENT, "limit_price", order.limit_price, expected_limit, order.client_order_id))
        expected_trigger = getattr(expected, "entry_trigger_price", None) if hasattr(expected, "entry_trigger_price") else getattr(expected, "trigger_price", None)
        if order.trigger_price != expected_trigger:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORDER_TRIGGER_PRICE_MISMATCH, "Order trigger price differs from expected price.", ReconciliationBoundary.ORDER_MANAGEMENT, "trigger_price", order.trigger_price, expected_trigger, order.client_order_id))
        if order.filled_quantity < 0 or order.filled_quantity > order.quantity:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.INVALID_ORDER_STATE, "Order filled quantity is invalid.", ReconciliationBoundary.ORDER_MANAGEMENT, "filled_quantity", order.filled_quantity, f"0..{order.quantity}", order.client_order_id))
        if order.remaining_quantity < 0 or order.filled_quantity + order.remaining_quantity != order.quantity:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.REMAINING_QUANTITY_MISMATCH, "Order remaining quantity does not reconcile to quantity.", ReconciliationBoundary.ORDER_MANAGEMENT, "remaining_quantity", order.remaining_quantity, order.quantity - order.filled_quantity, order.client_order_id))
        if purpose != "entry" and not reference.reduce_only:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.PROTECTIVE_REDUCE_ONLY_MISMATCH, "Protective order reference is not reduce-only.", ReconciliationBoundary.COORDINATOR_RECEIPT, "reduce_only", reference.reduce_only, True, reference.order_id))
        if policy.require_managed_submission_for_every_order:
            self._check_submission(purpose, order, submission, findings, timestamp, plan_for_submission)

    def _check_submission(self, purpose, order, submission, findings, timestamp, plan) -> None:
        if submission is None:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.MANAGED_SUBMISSION_NOT_FOUND, "Managed paper submission was not found.", ReconciliationBoundary.PAPER_TRADING, "order_id", order.client_order_id, None, order.client_order_id))
            return
        if not isinstance(submission, ManagedPaperSubmission):
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.INVALID_MANAGED_SUBMISSION, "Managed submission has an invalid type.", ReconciliationBoundary.PAPER_TRADING, related=order.client_order_id))
            return
        if submission.order_id != order.client_order_id:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORPHANED_MANAGED_SUBMISSION, "Managed submission references a different order.", ReconciliationBoundary.PAPER_TRADING, "order_id", submission.order_id, order.client_order_id, submission.submission_id))
        if plan is not None and submission.execution_plan_id != plan.execution_plan_id:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.EXECUTION_PLAN_ID_MISMATCH, "Managed submission references a different execution plan.", ReconciliationBoundary.PAPER_TRADING, "execution_plan_id", submission.execution_plan_id, plan.execution_plan_id, submission.submission_id))
        if submission.purpose != purpose:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORDER_PURPOSE_MISMATCH, "Managed submission purpose differs from expected purpose.", ReconciliationBoundary.PAPER_TRADING, "purpose", submission.purpose, purpose, submission.submission_id))
        if submission.instrument != order.symbol:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.INSTRUMENT_MISMATCH, "Managed submission instrument differs from order.", ReconciliationBoundary.PAPER_TRADING, "instrument", submission.instrument, order.symbol, submission.submission_id))
        if submission.order_quantity != order.quantity:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORDER_QUANTITY_MISMATCH, "Managed submission quantity differs from order.", ReconciliationBoundary.PAPER_TRADING, "order_quantity", submission.order_quantity, order.quantity, submission.submission_id))
        if submission.filled_quantity != order.filled_quantity:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.FILLED_QUANTITY_MISMATCH, "Managed submission filled quantity differs from order.", ReconciliationBoundary.PAPER_TRADING, "filled_quantity", submission.filled_quantity, order.filled_quantity, submission.submission_id))
        expected_status = EXPECTED_MANAGED_STATUS[order.status]
        if submission.status is not expected_status:
            reason = ReconciliationReasonCode.TERMINAL_STATE_REGRESSION if submission.status in TERMINAL_MANAGED_STATUSES and expected_status not in TERMINAL_MANAGED_STATUSES else ReconciliationReasonCode.MANAGED_STATUS_MISMATCH
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, reason, "Managed submission status differs from order status.", ReconciliationBoundary.PAPER_TRADING, "status", submission.status.value, expected_status.value, submission.submission_id))

    def _check_protection_lifecycle(self, timestamp, plan, receipt, entry_order, stop_order, target_order, findings, policy) -> None:
        full_entry_fill = entry_order is not None and entry_order.filled_quantity == entry_order.quantity and entry_order.status is OrderStatus.FILLED
        before_full_fill = entry_order is None or entry_order.filled_quantity < entry_order.quantity
        if before_full_fill:
            if stop_order is not None:
                findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.PROTECTION_CREATED_BEFORE_ENTRY_FILL, "Stop protection exists before full entry fill.", ReconciliationBoundary.CROSS_BOUNDARY, related=stop_order.client_order_id))
            if target_order is not None:
                findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.PROTECTION_CREATED_BEFORE_ENTRY_FILL, "Target protection exists before full entry fill.", ReconciliationBoundary.CROSS_BOUNDARY, related=target_order.client_order_id))
        if full_entry_fill and receipt.status not in {PaperExecutionStatus.FAILED, PaperExecutionStatus.CANCELLED, PaperExecutionStatus.REJECTED, PaperExecutionStatus.EXPIRED}:
            if policy.require_stop_when_planned and plan.stop_plan is not None and stop_order is None:
                findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.MISSING_STOP_PROTECTION, "Planned stop protection is missing after full entry fill.", ReconciliationBoundary.CROSS_BOUNDARY, related=receipt.receipt_id))
            if policy.require_target_when_planned and plan.target_plan is not None and target_order is None:
                findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.MISSING_TARGET_PROTECTION, "Planned target protection is missing after full entry fill.", ReconciliationBoundary.CROSS_BOUNDARY, related=receipt.receipt_id))

    def _check_receipt_status(self, timestamp, receipt, entry_order, stop_order, target_order, position, findings, policy) -> None:
        if receipt.status is PaperExecutionStatus.CANCELLED:
            for order in (entry_order, stop_order, target_order):
                if order is not None and order.status in ACTIVE_ORDER_STATUSES:
                    findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.CANCELLED_RECEIPT_HAS_ACTIVE_ORDER, "Cancelled receipt has an active order.", ReconciliationBoundary.CROSS_BOUNDARY, "status", order.status.value, "terminal", order.client_order_id))
        if receipt.status is PaperExecutionStatus.COMPLETED:
            if position is not None and position.status is PositionStatus.OPEN and position.absolute_quantity > 0:
                findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.COMPLETED_RECEIPT_HAS_OPEN_POSITION, "Completed receipt has an open position.", ReconciliationBoundary.POSITION, "position_status", position.status.value, PositionStatus.CLOSED.value, _position_id(position)))
            if policy.require_opposite_protection_cancel_after_exit:
                self._check_opposite_cancelled(timestamp, stop_order, target_order, findings)
        if receipt.status in ACTIVE_RECEIPT_STATUSES and position is not None and position.status is PositionStatus.CLOSED:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ACTIVE_RECEIPT_HAS_CLOSED_POSITION, "Active receipt has a closed position.", ReconciliationBoundary.POSITION, "position_status", position.status.value, PositionStatus.OPEN.value, _position_id(position)))

    def _check_opposite_cancelled(self, timestamp, stop_order, target_order, findings) -> None:
        if stop_order is not None and stop_order.status is OrderStatus.FILLED and target_order is not None and target_order.status in ACTIVE_ORDER_STATUSES:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.OPPOSITE_PROTECTION_NOT_CANCELLED, "Target protection remains active after stop fill.", ReconciliationBoundary.CROSS_BOUNDARY, "status", target_order.status.value, OrderStatus.CANCELLED.value, target_order.client_order_id))
        if target_order is not None and target_order.status is OrderStatus.FILLED and stop_order is not None and stop_order.status in ACTIVE_ORDER_STATUSES:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.OPPOSITE_PROTECTION_NOT_CANCELLED, "Stop protection remains active after target fill.", ReconciliationBoundary.CROSS_BOUNDARY, "status", stop_order.status.value, OrderStatus.CANCELLED.value, stop_order.client_order_id))

    def _check_position(self, timestamp, plan, receipt, entry_order, position, findings, policy) -> None:
        full_entry_fill = entry_order is not None and entry_order.status is OrderStatus.FILLED and entry_order.filled_quantity == entry_order.quantity
        if full_entry_fill and policy.require_position_after_entry_fill and receipt.status not in TERMINAL_RECEIPT_STATUSES and position is None:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.FILLED_ENTRY_WITHOUT_POSITION, "Entry is filled but no position is available.", ReconciliationBoundary.POSITION, related=receipt.receipt_id))
        if position is None:
            return
        if position.symbol != plan.instrument:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.POSITION_INSTRUMENT_MISMATCH, "Position instrument differs from execution plan.", ReconciliationBoundary.POSITION, "symbol", position.symbol, plan.instrument, _position_id(position)))
        expected_side = PositionSide.LONG if plan.entry_side is OrderSide.BUY else PositionSide.SHORT
        if full_entry_fill and position.status is PositionStatus.OPEN and position.side is not expected_side:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.INVALID_POSITION_STATE, "Position side differs from entry side.", ReconciliationBoundary.POSITION, "side", position.side.value, expected_side.value, _position_id(position)))
        if full_entry_fill and position.status is PositionStatus.OPEN and position.absolute_quantity != entry_order.filled_quantity:
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.POSITION_QUANTITY_MISMATCH, "Position quantity differs from filled entry quantity.", ReconciliationBoundary.POSITION, "quantity", position.absolute_quantity, entry_order.filled_quantity, _position_id(position)))

    def _check_orphans(self, timestamp, plan, receipt, refs, findings) -> None:
        referenced_order_ids = {ref.order_id for ref in refs.values() if ref is not None}
        all_orders = self._read_orders()
        for order in all_orders:
            if order.symbol != self._instrument:
                continue
            if plan.execution_plan_id in order.client_order_id and order.client_order_id not in referenced_order_ids:
                findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORPHANED_ORDER, "Order Management order belongs to plan but is not referenced by receipt.", ReconciliationBoundary.ORDER_MANAGEMENT, "order_id", order.client_order_id, "receipt reference", order.client_order_id))
        snapshot = self._read_paper_snapshot()
        if snapshot is None:
            return
        for submission in snapshot.managed_submissions:
            if submission.instrument != self._instrument:
                continue
            if submission.execution_plan_id == plan.execution_plan_id and submission.order_id not in referenced_order_ids:
                findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.ORPHANED_MANAGED_SUBMISSION, "Managed submission belongs to plan but is not referenced by receipt.", ReconciliationBoundary.PAPER_TRADING, "order_id", submission.order_id, "receipt reference", submission.submission_id))

    def _detect_duplicate_references(self, timestamp, refs, receipt, findings) -> None:
        order_ids = [ref.order_id for ref in refs.values() if ref is not None]
        if len(order_ids) != len(set(order_ids)):
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.DUPLICATE_ORDER_IDENTITY, "Receipt contains duplicate order identities.", ReconciliationBoundary.COORDINATOR_RECEIPT, "order_id", ",".join(order_ids), "unique", receipt.receipt_id))
        submission_ids = [value for value in (receipt.paper_submission_id, receipt.stop_paper_submission_id, receipt.target_paper_submission_id) if value is not None]
        if len(submission_ids) != len(set(submission_ids)):
            findings.append(self._finding(timestamp, ReconciliationSeverity.ERROR, ReconciliationReasonCode.DUPLICATE_SUBMISSION_IDENTITY, "Receipt contains duplicate managed submission identities.", ReconciliationBoundary.COORDINATOR_RECEIPT, "submission_id", ",".join(submission_ids), "unique", receipt.receipt_id))

    def _read_order(self, order_id: str | None) -> OrderState | None:
        if order_id is None:
            return None
        self._order_reads += 1
        return self._order_engine.get_order(order_id)

    def _read_orders(self) -> tuple[OrderState, ...]:
        self._order_reads += 1
        return self._order_engine.get_orders()

    def _read_submission(self, identity: str | None) -> ManagedPaperSubmission | None:
        if identity is None:
            return None
        self._paper_reads += 1
        return self._paper_engine.managed_submission(identity)

    def _read_paper_snapshot(self):
        self._paper_reads += 1
        return self._paper_engine.snapshot()

    def _read_position(self) -> PositionState | None:
        self._position_reads += 1
        return self._position_engine.state

    def _lookup_receipt(self, receipt_id: str) -> PaperExecutionReceipt | None:
        if self._coordinator is None or not hasattr(self._coordinator, "get_receipt"):
            return None
        return self._coordinator.get_receipt(receipt_id)

    def _lookup_plan(self, plan_id: str) -> TradeExecutionPlan | None:
        if self._coordinator is not None and hasattr(self._coordinator, "get_execution_plan_for_receipt"):
            receipt = self._lookup_receipt_by_plan(plan_id)
            if receipt is not None:
                plan = self._coordinator.get_execution_plan_for_receipt(receipt.receipt_id)
                if plan is not None:
                    return plan
        if self._execution_policy_engine is not None and hasattr(self._execution_policy_engine, "get_plan"):
            return self._execution_policy_engine.get_plan(plan_id)
        return None

    def _lookup_receipt_by_plan(self, plan_id: str) -> PaperExecutionReceipt | None:
        if self._coordinator is None or not hasattr(self._coordinator, "get_receipt_for_plan"):
            return None
        return self._coordinator.get_receipt_for_plan(plan_id)

    def _store_report(self, request, report, request_fp) -> None:
        self._reports[report.report_id] = report
        self._request_fingerprints[request.request_id] = request_fp
        self._request_reports[request.request_id] = report.report_id
        self._input_reports[report.input_fingerprint] = report.report_id
        self._last_report = report
        self._data = report
        self._reconciliation_count += 1
        if report.reconciliation_status is ReconciliationStatus.CONSISTENT:
            self._consistent_count += 1
        elif report.reconciliation_status is ReconciliationStatus.CONSISTENT_WITH_WARNINGS:
            self._warning_count += 1
        elif report.reconciliation_status in {ReconciliationStatus.INCONSISTENT, ReconciliationStatus.INCOMPLETE}:
            self._inconsistent_count += 1
        elif report.reconciliation_status is ReconciliationStatus.INVALID:
            self._invalid_count += 1
        elif report.reconciliation_status is ReconciliationStatus.FAILED:
            self._failed_count += 1
        self._findings = tuple((self._findings + report.findings)[-self._policy.maximum_findings :])
        if self._state is not ReconciliationLifecycleState.FAILED:
            self._state = ReconciliationLifecycleState.ACTIVE

    def _blocked_report(self, request, reason, message) -> ExecutionReconciliationReport:
        return self._minimal_request_report(request, reason, message, ReconciliationBoundary.CROSS_BOUNDARY, ReconciliationStatus.INVALID)

    def _duplicate_conflict_report(self, request, request_fp, existing_fp) -> ExecutionReconciliationReport:
        return self._minimal_request_report(
            request,
            ReconciliationReasonCode.INVALID_REQUEST,
            "Request ID was reused with different reconciliation content.",
            ReconciliationBoundary.CROSS_BOUNDARY,
            ReconciliationStatus.INVALID,
            field_name="request_id",
            observed=request_fp,
            expected=existing_fp,
        )

    def _failed_report(self, request, request_fp, exc) -> ExecutionReconciliationReport:
        return self._minimal_request_report(
            request,
            ReconciliationReasonCode.INTERNAL_RECONCILIATION_ERROR,
            _safe_message(exc),
            ReconciliationBoundary.CROSS_BOUNDARY,
            ReconciliationStatus.FAILED,
            severity=ReconciliationSeverity.CRITICAL,
            input_fingerprint=f"failed:{request_fp}:{exc.__class__.__name__}",
        )

    def _minimal_request_report(self, request, reason, message, boundary, status, *, severity=ReconciliationSeverity.ERROR, field_name=None, observed=None, expected=None, input_fingerprint=None) -> ExecutionReconciliationReport:
        return self._minimal_report(
            request.timestamp,
            instrument=request.instrument,
            plan_id=request.execution_plan.execution_plan_id,
            plan_fingerprint=request.execution_plan.input_fingerprint,
            receipt_id=request.execution_receipt.receipt_id,
            receipt_status=request.execution_receipt.status.value,
            request_fingerprint=request.fingerprint(),
            reason=reason,
            message=message,
            boundary=boundary,
            status=status,
            severity=severity,
            field_name=field_name,
            observed=observed,
            expected=expected,
            input_fingerprint=input_fingerprint,
            correlation_id=request.correlation_id,
            session_id=request.session_id,
        )

    def _minimal_report(self, timestamp, *, instrument, plan_id, plan_fingerprint, receipt_id, receipt_status, request_fingerprint, reason, message, boundary, status, severity=ReconciliationSeverity.ERROR, field_name=None, observed=None, expected=None, input_fingerprint=None, correlation_id=None, session_id=None) -> ExecutionReconciliationReport:
        finding = self._finding(timestamp, severity, reason, message, boundary, field_name, observed, expected, receipt_id)
        input_fp = input_fingerprint or model_fingerprint({"reason": reason.value, "receipt": receipt_id, "request": request_fingerprint, "observed": observed, "expected": expected})
        return ExecutionReconciliationReport(
            report_id=model_fingerprint({"minimal": request_fingerprint, "input": input_fp}),
            created_at=timestamp,
            instrument=instrument,
            execution_plan_id=plan_id,
            execution_plan_fingerprint=plan_fingerprint,
            receipt_id=receipt_id,
            receipt_status=receipt_status,
            reconciliation_status=status,
            primary_reason=reason,
            findings=(finding,),
            entry=None,
            stop=None,
            target=None,
            position_id=None,
            position_status=None,
            position_quantity=None,
            checked_boundaries=(boundary,),
            request_fingerprint=request_fingerprint,
            input_fingerprint=input_fp,
            order_management_read_count=self._order_reads,
            paper_trading_read_count=self._paper_reads,
            position_read_count=self._position_reads,
            broker_order_calls=0,
            mutation_calls=0,
            correlation_id=correlation_id,
            session_id=session_id,
        )

    def _finding(self, timestamp, severity, reason, message, boundary, field_name=None, observed=None, expected=None, related=None) -> ReconciliationFinding:
        return ReconciliationFinding(
            finding_id=finding_identity(timestamp, severity, reason, boundary, message, field_name, observed, expected, related),
            timestamp=timestamp,
            severity=severity,
            reason_code=reason,
            message=message,
            boundary=boundary,
            field_name=field_name,
            observed_value=None if observed is None else str(getattr(observed, "value", observed)),
            expected_value=None if expected is None else str(getattr(expected, "value", expected)),
            related_identity=None if related is None else str(related),
        )

    def _publish_report(self, report) -> None:
        self._publish(events.EXECUTION_RECONCILIATION_COMPLETED, report)
        if report.reconciliation_status is ReconciliationStatus.CONSISTENT_WITH_WARNINGS:
            self._publish(events.EXECUTION_RECONCILIATION_WARNING, report)
        elif report.reconciliation_status in {ReconciliationStatus.INCONSISTENT, ReconciliationStatus.INCOMPLETE}:
            self._publish(events.EXECUTION_RECONCILIATION_INCONSISTENT, report)
        elif report.reconciliation_status is ReconciliationStatus.INVALID:
            self._publish(events.EXECUTION_RECONCILIATION_INVALID, report)
        elif report.reconciliation_status is ReconciliationStatus.FAILED:
            self._publish(events.EXECUTION_RECONCILIATION_FAILED, report)
        self._publish(events.EXECUTION_RECONCILIATION_STATE_UPDATED, self.snapshot())

    def _publish(self, event_name: str, payload) -> None:
        self._event_bus.publish(event_name, payload)


def _normalized_state(purpose: str, reference: CoordinatedOrderReference | None, order: OrderState | None, submission: ManagedPaperSubmission | None) -> ReconciledOrderState | None:
    if reference is None and order is None and submission is None:
        return None
    return ReconciledOrderState(
        purpose=purpose,
        order_id=getattr(order, "client_order_id", None) or getattr(reference, "order_id", None),
        managed_submission_id=getattr(submission, "submission_id", None),
        instrument=getattr(order, "symbol", None) or getattr(reference, "instrument", None) or getattr(submission, "instrument", None),
        side=getattr(order, "side", None) or getattr(reference, "side", None),
        order_type=getattr(order, "order_type", None) or getattr(reference, "order_type", None),
        quantity=getattr(order, "quantity", None) or getattr(reference, "quantity", None),
        filled_quantity=getattr(order, "filled_quantity", None),
        remaining_quantity=getattr(order, "remaining_quantity", None),
        limit_price=getattr(order, "limit_price", None) if order is not None else getattr(reference, "limit_price", None),
        trigger_price=getattr(order, "trigger_price", None) if order is not None else getattr(reference, "trigger_price", None),
        order_status=getattr(order, "status", None) or getattr(reference, "status", None),
        managed_status=getattr(submission, "status", None),
        reduce_only=bool(getattr(reference, "reduce_only", False)),
    )


def _sort_findings(findings: list[ReconciliationFinding]) -> tuple[ReconciliationFinding, ...]:
    return tuple(
        sorted(
            findings,
            key=lambda item: (
                SEVERITY_ORDER[item.severity],
                item.boundary.value,
                item.reason_code.value,
                item.related_identity or "",
                item.field_name or "",
                item.finding_id,
            ),
        )
    )


def _status_for(findings: tuple[ReconciliationFinding, ...]) -> ReconciliationStatus:
    if not findings:
        return ReconciliationStatus.CONSISTENT
    if any(item.reason_code is ReconciliationReasonCode.INTERNAL_RECONCILIATION_ERROR for item in findings):
        return ReconciliationStatus.FAILED
    if any(item.reason_code in {ReconciliationReasonCode.INVALID_REQUEST, ReconciliationReasonCode.INVALID_EXECUTION_PLAN, ReconciliationReasonCode.INVALID_RECEIPT} for item in findings):
        return ReconciliationStatus.INVALID
    if any(item.reason_code in INCOMPLETE_REASONS for item in findings):
        return ReconciliationStatus.INCOMPLETE
    if any(item.severity in {ReconciliationSeverity.ERROR, ReconciliationSeverity.CRITICAL} for item in findings):
        return ReconciliationStatus.INCONSISTENT
    return ReconciliationStatus.CONSISTENT_WITH_WARNINGS


def _primary_reason(findings: tuple[ReconciliationFinding, ...]) -> ReconciliationReasonCode:
    if not findings:
        return ReconciliationReasonCode.CONSISTENT
    return findings[0].reason_code


def _missing_order_reason(purpose: str) -> ReconciliationReasonCode:
    if purpose == "entry":
        return ReconciliationReasonCode.ENTRY_ORDER_NOT_FOUND
    if purpose == "stop_loss":
        return ReconciliationReasonCode.STOP_ORDER_NOT_FOUND
    if purpose == "target":
        return ReconciliationReasonCode.TARGET_ORDER_NOT_FOUND
    return ReconciliationReasonCode.ORDER_NOT_FOUND


def _position_id(position: PositionState | None) -> str | None:
    if position is None:
        return None
    return f"position:{position.symbol}:{position.timeframe}:{position.opened_at.isoformat() if position.opened_at is not None else 'none'}"


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


def _safe_message(exc) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    for token in ("api_key", "api_secret", "access_token", "request_token"):
        text = text.replace(token, "[REDACTED]")
    return text[:500]
