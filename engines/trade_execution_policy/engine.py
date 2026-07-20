"""
Synchronous Trade Execution Policy Engine V1.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from math import isfinite

from core.base_engine import BaseEngine
from core import events
from engines.order_management.enums import OrderSide, OrderType
from engines.risk.enums import RiskDecision, RiskDecisionStatus
from engines.strategy.enums import TradeDirection
from engines.trade_execution_policy.enums import (
    ExecutionDecisionStatus,
    ExecutionLifecycleState,
    ExecutionMode,
    ExecutionPlanStatus,
    ExecutionReasonCode,
    ExecutionRoutingTarget,
    ExecutionSeverity,
    ProtectiveOrderPurpose,
    ProtectiveOrderStatus,
)
from engines.trade_execution_policy.models import (
    ExecutionEngineSnapshot,
    ExecutionFinding,
    ExecutionPolicy,
    ExecutionRequest,
    ProtectiveOrderPlan,
    TradeExecutionPlan,
    build_valid_until,
    _fingerprint,
    _model_payload,
)


ACTIVE_STATUSES = {
    ExecutionPlanStatus.PREPARED,
    ExecutionPlanStatus.AWAITING_MANUAL_APPROVAL,
    ExecutionPlanStatus.READY_FOR_PAPER,
}


class TradeExecutionPolicyEngine(BaseEngine):
    """
    Converts an approved risk decision into an immutable execution plan.

    This engine never places, modifies, cancels, submits, simulates, or routes a
    broker order. It owns only deterministic execution-policy validation and
    immutable plan preparation.
    """

    def __init__(self, event_bus, *, instrument: str, timeframe: str, policy: ExecutionPolicy | None = None):
        super().__init__(event_bus)
        self._instrument = str(instrument).strip().upper()
        self._timeframe = str(timeframe).strip()
        self._policy = policy or ExecutionPolicy()
        if not isinstance(self._policy, ExecutionPolicy):
            raise TypeError("policy must be ExecutionPolicy")
        self._state = ExecutionLifecycleState.CREATED
        self._plans: dict[str, TradeExecutionPlan] = {}
        self._by_client_request: dict[str, str] = {}
        self._by_risk_decision: dict[str, str] = {}
        self._by_signal: dict[str, str] = {}
        self._last_plan: TradeExecutionPlan | None = None
        self._findings: tuple[ExecutionFinding, ...] = ()
        self._evaluation_count = 0
        self._approved_count = 0
        self._rejected_count = 0
        self._locked_count = 0
        self._expired_count = 0

    @property
    def policy(self) -> ExecutionPolicy:
        return self._policy

    @property
    def last_plan(self) -> TradeExecutionPlan | None:
        return self._last_plan

    def start(self) -> ExecutionEngineSnapshot:
        if self._state is not ExecutionLifecycleState.STOPPED:
            self._state = ExecutionLifecycleState.READY
        self._publish(events.EXECUTION_POLICY_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def stop(self) -> ExecutionEngineSnapshot:
        self._state = ExecutionLifecycleState.STOPPED
        self._publish(events.EXECUTION_POLICY_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def evaluate(self, request: ExecutionRequest, policy: ExecutionPolicy | None = None) -> TradeExecutionPlan:
        if not isinstance(request, ExecutionRequest):
            raise TypeError("request must be ExecutionRequest")
        active_policy = policy or self._policy
        if not isinstance(active_policy, ExecutionPolicy):
            raise TypeError("policy must be ExecutionPolicy")
        self._evaluation_count += 1
        if self._state is ExecutionLifecycleState.CREATED:
            self._state = ExecutionLifecycleState.READY
        if self._state is ExecutionLifecycleState.STOPPED:
            plan = self._blocked_plan(request, active_policy, ExecutionDecisionStatus.LOCKED, ExecutionReasonCode.ENGINE_STOPPED, "Execution policy engine is stopped.")
            self._store_terminal(plan)
            return plan
        if self._state is ExecutionLifecycleState.LOCKED:
            plan = self._blocked_plan(request, active_policy, ExecutionDecisionStatus.LOCKED, ExecutionReasonCode.ENGINE_LOCKED, "Execution policy engine is locked.")
            self._store_terminal(plan)
            return plan

        try:
            duplicate = self._idempotent_duplicate(request, active_policy)
            if duplicate is not None:
                self._publish(events.EXECUTION_POLICY_EVALUATED, duplicate)
                return duplicate
            plan = self._evaluate(request, active_policy)
        except Exception as exc:
            self._state = ExecutionLifecycleState.FAILED
            plan = self._blocked_plan(
                request,
                active_policy,
                ExecutionDecisionStatus.INVALID,
                ExecutionReasonCode.INTERNAL_VALIDATION_ERROR,
                _safe_message(exc),
            )
        if plan.decision_status is ExecutionDecisionStatus.APPROVED:
            self._store_active(plan)
            self._approved_count += 1
            self._state = ExecutionLifecycleState.ACTIVE
            self._publish(events.EXECUTION_PLAN_PREPARED, plan)
        elif plan.decision_status is ExecutionDecisionStatus.LOCKED:
            self._store_active(plan) if plan.status in ACTIVE_STATUSES else self._store_terminal(plan)
            self._locked_count += 1
            self._publish(events.EXECUTION_PLAN_LOCKED, plan)
        elif plan.decision_status is ExecutionDecisionStatus.EXPIRED:
            self._store_terminal(plan)
            self._expired_count += 1
            self._publish(events.EXECUTION_PLAN_EXPIRED, plan)
        else:
            self._store_terminal(plan)
            self._rejected_count += 1
            self._publish(events.EXECUTION_PLAN_REJECTED, plan)
        self._publish(events.EXECUTION_POLICY_EVALUATED, plan)
        self._publish(events.EXECUTION_POLICY_STATE_UPDATED, self.snapshot())
        return plan

    def approve_manual(self, execution_plan_id: str, *, timestamp: datetime) -> TradeExecutionPlan:
        _aware(timestamp, "timestamp")
        plan = self._plans.get(_text(execution_plan_id, "execution_plan_id"))
        if plan is None:
            raise ValueError("Unknown execution plan.")
        if not _manual_approval_eligible(plan, timestamp):
            raise ValueError("Plan is not eligible for manual approval.")
        status = ExecutionPlanStatus.READY_FOR_PAPER if plan.execution_mode is ExecutionMode.PAPER else ExecutionPlanStatus.PREPARED
        approved = replace(
            plan,
            manual_approval_present=True,
            status=status,
            decision_status=ExecutionDecisionStatus.APPROVED,
            primary_reason=ExecutionReasonCode.APPROVED,
            findings=(),
        )
        self._store_active(approved)
        self._approved_count += 1
        self._publish(events.EXECUTION_PLAN_APPROVED, approved)
        self._publish(events.EXECUTION_POLICY_STATE_UPDATED, self.snapshot())
        return approved

    def cancel_plan(self, execution_plan_id: str, *, timestamp: datetime, reason: str = "cancelled") -> TradeExecutionPlan:
        _aware(timestamp, "timestamp")
        plan = self._plans.get(_text(execution_plan_id, "execution_plan_id"))
        if plan is None:
            raise ValueError("Unknown execution plan.")
        cancelled = replace(
            plan,
            status=ExecutionPlanStatus.CANCELLED,
            decision_status=ExecutionDecisionStatus.REJECTED,
            primary_reason=ExecutionReasonCode.INVALID_REQUEST,
            findings=(self._finding(timestamp, ExecutionSeverity.INFO, ExecutionReasonCode.INVALID_REQUEST, reason, "execution_plan_id", plan.execution_plan_id),),
        )
        self._store_terminal(cancelled)
        self._publish(events.EXECUTION_PLAN_CANCELLED, cancelled)
        self._publish(events.EXECUTION_POLICY_STATE_UPDATED, self.snapshot())
        return cancelled

    def expire_plan(self, execution_plan_id: str, *, timestamp: datetime) -> TradeExecutionPlan:
        _aware(timestamp, "timestamp")
        plan = self._plans.get(_text(execution_plan_id, "execution_plan_id"))
        if plan is None:
            raise ValueError("Unknown execution plan.")
        expired = replace(
            plan,
            status=ExecutionPlanStatus.EXPIRED,
            decision_status=ExecutionDecisionStatus.EXPIRED,
            primary_reason=ExecutionReasonCode.REQUEST_EXPIRED,
            findings=(self._finding(timestamp, ExecutionSeverity.WARNING, ExecutionReasonCode.REQUEST_EXPIRED, "Execution plan expired.", "valid_until", timestamp.isoformat(), plan.valid_until.isoformat()),),
        )
        self._expired_count += 1
        self._store_terminal(expired)
        self._publish(events.EXECUTION_PLAN_EXPIRED, expired)
        self._publish(events.EXECUTION_POLICY_STATE_UPDATED, self.snapshot())
        return expired

    def reset_session(self) -> ExecutionEngineSnapshot:
        self._plans.clear()
        self._by_client_request.clear()
        self._by_risk_decision.clear()
        self._by_signal.clear()
        self._last_plan = None
        self._findings = ()
        self._state = ExecutionLifecycleState.READY
        self._publish(events.EXECUTION_POLICY_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def snapshot(self) -> ExecutionEngineSnapshot:
        active = tuple(plan.execution_plan_id for plan in self._plans.values() if plan.status in ACTIVE_STATUSES)
        return ExecutionEngineSnapshot(
            enabled=self._policy.enabled,
            lifecycle_state=self._state,
            last_plan=self._last_plan,
            evaluation_count=self._evaluation_count,
            approved_count=self._approved_count,
            rejected_count=self._rejected_count,
            locked_count=self._locked_count,
            expired_count=self._expired_count,
            active_plan_ids=active,
            findings=self._findings,
            broker_order_calls=0,
        )

    def _evaluate(self, request: ExecutionRequest, policy: ExecutionPolicy) -> TradeExecutionPlan:
        try:
            risk = _risk_view(request.risk_decision)
        except RiskInputValidationError:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.INVALID, ExecutionReasonCode.INVALID_RISK_DECISION, "Risk decision is invalid.")
        mode = request.execution_mode or policy.default_execution_mode
        if not policy.enabled:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.POLICY_DISABLED, "Execution policy is disabled.")
        if request.instrument != self._instrument:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.RISK_DECISION_MISMATCH, "Request instrument does not match runtime.", "instrument", request.instrument, self._instrument)
        if request.instrument not in policy.allowed_instruments:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.UNSUPPORTED_INSTRUMENT, "Instrument is not allowed.", "instrument", request.instrument)
        if isinstance(mode, str) and mode.strip().lower() == "live":
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.LIVE_EXECUTION_BLOCKED, "Live execution is blocked in V1.", "execution_mode", "live")
        if not isinstance(mode, ExecutionMode) or mode not in policy.allowed_execution_modes:
            observed_mode = mode.value if isinstance(mode, ExecutionMode) else str(mode)
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.UNSUPPORTED_EXECUTION_MODE, "Execution mode is not allowed.", "execution_mode", observed_mode)
        if not risk["valid"]:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.INVALID, ExecutionReasonCode.INVALID_RISK_DECISION, "Risk decision is invalid.")
        if policy.require_risk_approval and not risk["approved"]:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.RISK_NOT_APPROVED, "Risk decision is not approved.")
        if risk["instrument"] != request.instrument:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.RISK_DECISION_MISMATCH, "Risk decision instrument mismatch.", "instrument", risk["instrument"], request.instrument)
        age = (request.timestamp - risk["timestamp"]).total_seconds()
        if age > policy.maximum_decision_age_seconds:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.EXPIRED, ExecutionReasonCode.RISK_DECISION_EXPIRED, "Risk decision is stale.", "age_seconds", str(int(age)), str(policy.maximum_decision_age_seconds))
        quantity = request.requested_quantity if request.requested_quantity is not None else risk["approved_quantity"]
        if quantity <= 0:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.ZERO_QUANTITY, "Execution quantity must be positive.", "requested_quantity", str(quantity))
        if quantity > risk["approved_quantity"]:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.QUANTITY_INCREASE_BLOCKED, "Execution quantity cannot exceed approved risk quantity.", "requested_quantity", str(quantity), str(risk["approved_quantity"]))
        if quantity < risk["approved_quantity"] and not policy.allow_quantity_reduction:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.QUANTITY_MISMATCH, "Quantity reduction is not allowed.", "requested_quantity", str(quantity), str(risk["approved_quantity"]))
        if policy.quantity_must_match_risk_decision and quantity != risk["approved_quantity"]:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.QUANTITY_MISMATCH, "Execution quantity must match risk decision.", "requested_quantity", str(quantity), str(risk["approved_quantity"]))
        if request.requested_order_type not in policy.allowed_entry_order_types:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.UNSUPPORTED_ORDER_TYPE, "Order type is not allowed.", "order_type", request.requested_order_type.value)
        order_type_reason = _order_type_reason(request.requested_order_type, policy)
        if order_type_reason is not None:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, order_type_reason, "Order type is blocked by policy.", "order_type", request.requested_order_type.value)
        entry_price = request.requested_entry_price if request.requested_entry_price is not None else risk["entry_price"]
        reference = request.market_reference_price if request.market_reference_price is not None else risk["entry_price"]
        if entry_price <= 0 or reference <= 0:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.INVALID_ENTRY_PRICE, "Entry and market reference prices must be positive.")
        tick = policy.tick_size_for(request.instrument)
        if tick is None:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.UNSUPPORTED_INSTRUMENT, "Missing tick-size configuration.", "instrument", request.instrument)
        price_failure = self._validate_entry_prices(request, policy, risk, entry_price, tick)
        if price_failure is not None:
            return price_failure
        slippage = abs(entry_price - reference)
        if policy.maximum_entry_slippage_points is not None and slippage > policy.maximum_entry_slippage_points:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.SLIPPAGE_LIMIT_EXCEEDED, "Entry slippage exceeds point limit.", "slippage_points", str(round(slippage, 4)), str(policy.maximum_entry_slippage_points))
        slippage_pct = slippage / reference * 100
        if policy.maximum_entry_slippage_percentage is not None and slippage_pct > policy.maximum_entry_slippage_percentage:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.SLIPPAGE_LIMIT_EXCEEDED, "Entry slippage exceeds percentage limit.", "slippage_percentage", str(round(slippage_pct, 6)), str(policy.maximum_entry_slippage_percentage))
        if policy.require_stop_order and risk["stop_price"] is None:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.MISSING_STOP_PLAN, "Risk decision has no stop loss.")
        if policy.require_target_order and risk["target_price"] is None:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.MISSING_TARGET_PLAN, "Risk decision has no target.")
        protective_price_failure = self._validate_protective_prices(request, policy, risk, tick)
        if protective_price_failure is not None:
            return protective_price_failure
        geometry_failure = self._validate_geometry(request, policy, risk, entry_price)
        if geometry_failure is not None:
            return geometry_failure
        duplicate_failure = self._duplicate_failure(request, policy, risk)
        if duplicate_failure is not None:
            return duplicate_failure
        manual_required = policy.require_manual_approval or bool(risk["manual_approval_required"])
        valid_until = build_valid_until(request.timestamp, policy, request.valid_until)
        plan_id = _plan_id(request, policy, risk)
        stop, target = self._protective_plans(plan_id, request, risk, quantity)
        routing = ExecutionRoutingTarget.PAPER_TRADING if mode is ExecutionMode.PAPER else ExecutionRoutingTarget.PLAN_ONLY
        if manual_required and not request.manual_approval:
            finding = self._finding(request.timestamp, ExecutionSeverity.WARNING, ExecutionReasonCode.MISSING_MANUAL_APPROVAL, "Manual approval is required before routing.", "manual_approval", "False", "True")
            return self._plan(request, policy, risk, plan_id, mode, quantity, entry_price, reference, valid_until, stop, target, routing, ExecutionPlanStatus.AWAITING_MANUAL_APPROVAL, ExecutionDecisionStatus.LOCKED, ExecutionReasonCode.MISSING_MANUAL_APPROVAL, (finding,), manual_required)
        status = ExecutionPlanStatus.READY_FOR_PAPER if mode is ExecutionMode.PAPER else ExecutionPlanStatus.PREPARED
        return self._plan(request, policy, risk, plan_id, mode, quantity, entry_price, reference, valid_until, stop, target, routing, status, ExecutionDecisionStatus.APPROVED, ExecutionReasonCode.APPROVED, (), manual_required)

    def _validate_entry_prices(self, request, policy, risk, entry_price, tick):
        if request.requested_order_type is OrderType.MARKET:
            return None
        if not _tick_aligned(entry_price, tick):
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.PRICE_NOT_TICK_ALIGNED, "Entry limit price is not tick aligned.", "requested_entry_price", str(entry_price), str(tick))
        if request.requested_order_type is OrderType.LIMIT:
            return None
        trigger = request.trigger_price
        if trigger is None:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.INVALID_TRIGGER_PRICE, "STOP_LIMIT requires trigger price.", "trigger_price", None)
        if not _tick_aligned(trigger, tick):
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.PRICE_NOT_TICK_ALIGNED, "Trigger price is not tick aligned.", "trigger_price", str(trigger), str(tick))
        side = _entry_side(risk["direction"])
        if side is OrderSide.BUY and entry_price < trigger:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.INVALID_LIMIT_PRICE, "BUY stop-limit requires limit >= trigger.")
        if side is OrderSide.SELL and entry_price > trigger:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.INVALID_LIMIT_PRICE, "SELL stop-limit requires limit <= trigger.")
        return None

    def _validate_protective_prices(self, request, policy, risk, tick):
        stop = risk["stop_price"]
        if stop is not None and (not isfinite(stop) or stop <= 0):
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.INVALID_STOP_PRICE, "Stop price must be finite and positive.", "stop_price", str(stop))
        if stop is not None and not _tick_aligned(stop, tick):
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.INVALID_STOP_PRICE, "Stop price is not tick aligned.", "stop_price", str(stop), str(tick))
        target = risk["target_price"]
        if target is not None and (not isfinite(target) or target <= 0):
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.INVALID_TARGET_PRICE, "Target price must be finite and positive.", "target_price", str(target))
        if target is not None and not _tick_aligned(target, tick):
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.INVALID_TARGET_PRICE, "Target price is not tick aligned.", "target_price", str(target), str(tick))
        return None

    def _validate_geometry(self, request, policy, risk, entry_price):
        stop = risk["stop_price"]
        target = risk["target_price"]
        if stop is not None and risk["direction"] is TradeDirection.BULLISH and not stop < entry_price:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.INVALID_STOP_GEOMETRY, "Bullish stop must be below entry.")
        if stop is not None and risk["direction"] is TradeDirection.BEARISH and not stop > entry_price:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.INVALID_STOP_GEOMETRY, "Bearish stop must be above entry.")
        if target is not None and risk["direction"] is TradeDirection.BULLISH and not target > entry_price:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.INVALID_TARGET_GEOMETRY, "Bullish target must be above entry.")
        if target is not None and risk["direction"] is TradeDirection.BEARISH and not target < entry_price:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.INVALID_TARGET_GEOMETRY, "Bearish target must be below entry.")
        return None

    def _duplicate_failure(self, request, policy, risk):
        if policy.allow_duplicate_plan:
            return None
        if request.client_request_id and request.client_request_id in self._by_client_request:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.DUPLICATE_EXECUTION_PLAN, "Client request already has an active execution plan.", "client_request_id", request.client_request_id)
        if policy.one_active_plan_per_risk_decision and risk["decision_id"] in self._by_risk_decision:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.RISK_DECISION_ALREADY_HAS_PLAN, "Risk decision already has an active execution plan.", "risk_decision_id", risk["decision_id"])
        signal_id = request.signal_id or risk["signal_id"]
        if policy.one_active_plan_per_signal and signal_id and signal_id in self._by_signal:
            return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.SIGNAL_ALREADY_HAS_PLAN, "Signal already has an active execution plan.", "signal_id", signal_id)
        for plan_id in request.existing_active_plan_ids:
            if plan_id in self._plans and self._plans[plan_id].status in ACTIVE_STATUSES:
                return self._blocked_plan(request, policy, ExecutionDecisionStatus.REJECTED, ExecutionReasonCode.DUPLICATE_EXECUTION_PLAN, "Existing active plan blocks duplicate preparation.", "execution_plan_id", plan_id)
        return None

    def _idempotent_duplicate(self, request, policy) -> TradeExecutionPlan | None:
        request_fp = request.fingerprint()
        for plan in self._plans.values():
            if plan.request_fingerprint == request_fp and plan.status in ACTIVE_STATUSES:
                return plan
        return None

    def _protective_plans(self, plan_id, request, risk, quantity):
        side = _protective_side(risk["direction"])
        stop = None
        target = None
        if risk["stop_price"] is not None:
            stop = ProtectiveOrderPlan(
                purpose=ProtectiveOrderPurpose.STOP_LOSS,
                side=side,
                order_type=OrderType.STOP_LIMIT,
                quantity=quantity,
                trigger_price=risk["stop_price"],
                limit_price=risk["stop_price"],
                reduce_only=True,
                parent_execution_plan_id=plan_id,
                status=ProtectiveOrderStatus.PLANNED,
            )
        if risk["target_price"] is not None:
            target = ProtectiveOrderPlan(
                purpose=ProtectiveOrderPurpose.TARGET,
                side=side,
                order_type=OrderType.LIMIT,
                quantity=quantity,
                trigger_price=None,
                limit_price=risk["target_price"],
                reduce_only=True,
                parent_execution_plan_id=plan_id,
                status=ProtectiveOrderStatus.PLANNED,
            )
        return stop, target

    def _plan(self, request, policy, risk, plan_id, mode, quantity, entry_price, reference, valid_until, stop, target, routing, status, decision_status, reason, findings, manual_required):
        request_fp = request.fingerprint()
        policy_fp = policy.fingerprint()
        input_fp = _fingerprint({"policy": policy_fp, "request": request_fp, "risk": risk["fingerprint"]})
        return TradeExecutionPlan(
            execution_plan_id=plan_id,
            created_at=request.timestamp,
            valid_from=request.timestamp,
            valid_until=valid_until,
            instrument=request.instrument,
            direction=risk["direction"],
            entry_side=_entry_side(risk["direction"]),
            execution_mode=mode,
            entry_order_type=request.requested_order_type,
            entry_quantity=quantity,
            entry_limit_price=entry_price if request.requested_order_type is not OrderType.MARKET else None,
            entry_trigger_price=request.trigger_price,
            market_reference_price=reference,
            risk_decision_id=risk["decision_id"],
            risk_decision_fingerprint=risk["fingerprint"],
            signal_id=request.signal_id or risk["signal_id"] or "-",
            strategy_id=request.strategy_id or risk["strategy_id"] or "-",
            client_request_id=request.client_request_id or "-",
            stop_plan=stop,
            target_plan=target,
            manual_approval_required=manual_required,
            manual_approval_present=request.manual_approval,
            routing_target=routing,
            status=status,
            decision_status=decision_status,
            primary_reason=reason,
            findings=tuple(findings),
            policy_fingerprint=policy_fp,
            request_fingerprint=request_fp,
            input_fingerprint=input_fp,
            broker_submission_allowed=False,
            broker_order_calls=0,
        )

    def _blocked_plan(self, request, policy, status, reason, message, field_name=None, observed=None, limit=None):
        risk = _risk_view(request.risk_decision, tolerate_invalid=True)
        mode = request.execution_mode or policy.default_execution_mode
        if not isinstance(mode, ExecutionMode):
            mode = policy.default_execution_mode
        entry = request.requested_entry_price or risk.get("entry_price") or request.market_reference_price or 1.0
        reference = request.market_reference_price or entry
        valid_until = build_valid_until(request.timestamp, policy, request.valid_until)
        finding = self._finding(request.timestamp, ExecutionSeverity.ERROR, reason, message, field_name, observed, limit)
        return self._plan(
            request,
            policy,
            risk,
            _plan_id(request, policy, risk),
            mode,
            max(1, request.requested_quantity or risk.get("approved_quantity") or 1),
            entry,
            reference,
            valid_until,
            None,
            None,
            ExecutionRoutingTarget.PLAN_ONLY,
            _blocked_plan_status(status, reason),
            status,
            reason,
            (finding,),
            reason is ExecutionReasonCode.MISSING_MANUAL_APPROVAL,
        )

    def _finding(self, timestamp, severity, reason, message, field_name=None, observed=None, limit=None):
        payload = {
            "timestamp": timestamp.isoformat(),
            "severity": severity.value,
            "reason": reason.value,
            "message": message,
            "field": field_name,
            "observed": observed,
            "limit": limit,
        }
        return ExecutionFinding(
            finding_id=_fingerprint(payload),
            timestamp=timestamp,
            severity=severity,
            reason_code=reason,
            message=message,
            field_name=field_name,
            observed_value=None if observed is None else str(observed),
            limit_value=None if limit is None else str(limit),
            occurrence_count=1,
        )

    def _store_active(self, plan: TradeExecutionPlan) -> None:
        self._plans[plan.execution_plan_id] = plan
        if plan.client_request_id != "-":
            self._by_client_request[plan.client_request_id] = plan.execution_plan_id
        self._by_risk_decision[plan.risk_decision_id] = plan.execution_plan_id
        if plan.signal_id != "-":
            self._by_signal[plan.signal_id] = plan.execution_plan_id
        self._last_plan = plan
        self._data = plan

    def _store_terminal(self, plan: TradeExecutionPlan) -> None:
        existing = self._plans.get(plan.execution_plan_id)
        self._plans[plan.execution_plan_id] = plan
        if existing is not None and existing.status in ACTIVE_STATUSES and plan.status not in ACTIVE_STATUSES:
            self._by_client_request = {key: value for key, value in self._by_client_request.items() if value != plan.execution_plan_id}
            self._by_risk_decision = {key: value for key, value in self._by_risk_decision.items() if value != plan.execution_plan_id}
            self._by_signal = {key: value for key, value in self._by_signal.items() if value != plan.execution_plan_id}
        self._last_plan = plan
        self._findings = tuple((self._findings + plan.findings)[-50:])
        self._data = plan

    def _publish(self, event_name: str, payload) -> None:
        self._event_bus.publish(event_name, payload)


class RiskInputValidationError(ValueError):
    pass


def _risk_view(risk, *, tolerate_invalid: bool = False) -> dict[str, object]:
    try:
        timestamp = getattr(risk, "timestamp")
        _aware(timestamp, "risk.timestamp")
        instrument = str(getattr(risk, "instrument", getattr(risk, "symbol", ""))).strip().upper()
        direction = getattr(risk, "direction")
        if not isinstance(direction, TradeDirection) or direction is TradeDirection.NONE:
            raise ValueError("risk direction must be bullish or bearish")
        approved_quantity = int(getattr(risk, "approved_quantity"))
        approved_lots = int(getattr(risk, "approved_lots", 0))
        entry_price = float(getattr(risk, "entry_price"))
        stop_price = getattr(risk, "stop_loss_price", getattr(risk, "stop_price", None))
        target_price = getattr(risk, "target_price", None)
        status = getattr(risk, "status", None)
        decision = getattr(risk, "decision", None)
        approved = bool(getattr(risk, "approved", False))
        if isinstance(status, RiskDecisionStatus):
            approved = status in {RiskDecisionStatus.APPROVED, RiskDecisionStatus.APPROVED_WITH_REDUCED_SIZE} and bool(getattr(risk, "approved", True))
        elif isinstance(decision, RiskDecision):
            approved = decision is RiskDecision.APPROVED and approved_quantity > 0
        decision_id = str(getattr(risk, "decision_id", getattr(risk, "plan_id", "")) or "")
        if not decision_id:
            decision_id = _fingerprint(_model_payload(risk))
        fingerprint = str(getattr(risk, "input_fingerprint", None) or getattr(risk, "plan_fingerprint", None) or _fingerprint(_model_payload(risk)))
        return {
            "valid": True,
            "timestamp": timestamp,
            "instrument": instrument,
            "direction": direction,
            "approved": approved,
            "approved_quantity": approved_quantity,
            "approved_lots": approved_lots,
            "entry_price": entry_price,
            "stop_price": None if stop_price is None else float(stop_price),
            "target_price": None if target_price is None else float(target_price),
            "decision_id": decision_id,
            "fingerprint": fingerprint,
            "signal_id": getattr(risk, "signal_id", None) or getattr(risk, "plan_id", None),
            "strategy_id": getattr(risk, "strategy_id", None) or getattr(risk, "plan_id", None),
            "manual_approval_required": bool(getattr(risk, "manual_approval_required", False)),
        }
    except (AttributeError, TypeError, ValueError) as exc:
        if not tolerate_invalid:
            raise RiskInputValidationError("Risk decision is invalid.") from exc
        timestamp = getattr(risk, "timestamp", None)
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
            from datetime import timezone

            timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return {
            "valid": False,
            "timestamp": timestamp,
            "instrument": "-",
            "direction": TradeDirection.BULLISH,
            "approved": False,
            "approved_quantity": 0,
            "approved_lots": 0,
            "entry_price": 1.0,
            "stop_price": None,
            "target_price": None,
            "decision_id": "invalid-risk-decision",
            "fingerprint": "invalid-risk-decision",
            "signal_id": None,
            "strategy_id": None,
            "manual_approval_required": False,
        }


def _blocked_plan_status(status: ExecutionDecisionStatus, reason: ExecutionReasonCode) -> ExecutionPlanStatus:
    if status is ExecutionDecisionStatus.LOCKED:
        if reason is ExecutionReasonCode.MISSING_MANUAL_APPROVAL:
            return ExecutionPlanStatus.AWAITING_MANUAL_APPROVAL
        return ExecutionPlanStatus.LOCKED
    return ExecutionPlanStatus.REJECTED


def _manual_approval_eligible(plan: TradeExecutionPlan, timestamp: datetime) -> bool:
    return (
        plan.status is ExecutionPlanStatus.AWAITING_MANUAL_APPROVAL
        and plan.decision_status is ExecutionDecisionStatus.LOCKED
        and plan.primary_reason is ExecutionReasonCode.MISSING_MANUAL_APPROVAL
        and plan.manual_approval_required is True
        and plan.manual_approval_present is False
        and timestamp < plan.valid_until
    )


def _entry_side(direction: TradeDirection) -> OrderSide:
    return OrderSide.BUY if direction is TradeDirection.BULLISH else OrderSide.SELL


def _protective_side(direction: TradeDirection) -> OrderSide:
    return OrderSide.SELL if direction is TradeDirection.BULLISH else OrderSide.BUY


def _order_type_reason(order_type: OrderType, policy: ExecutionPolicy) -> ExecutionReasonCode | None:
    if order_type is OrderType.MARKET and not policy.allow_market_orders:
        return ExecutionReasonCode.MARKET_ORDER_BLOCKED
    if order_type is OrderType.LIMIT and not policy.allow_limit_orders:
        return ExecutionReasonCode.UNSUPPORTED_ORDER_TYPE
    if order_type is OrderType.STOP_LIMIT and not policy.allow_stop_limit_orders:
        return ExecutionReasonCode.UNSUPPORTED_ORDER_TYPE
    return None


def _tick_aligned(price: float, tick: float) -> bool:
    units = price / tick
    return abs(units - round(units)) < 1e-9


def _plan_id(request: ExecutionRequest, policy: ExecutionPolicy, risk: dict[str, object]) -> str:
    return _fingerprint(
        {
            "instrument": request.instrument,
            "timestamp": request.timestamp.isoformat(),
            "risk_decision_id": risk["decision_id"],
            "risk_fingerprint": risk["fingerprint"],
            "request": request.fingerprint(),
            "policy": policy.fingerprint(),
        }
    )


def _safe_message(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text[:500]


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()
