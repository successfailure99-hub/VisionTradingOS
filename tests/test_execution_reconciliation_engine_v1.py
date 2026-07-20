from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from core import events
from core.event_bus import EventBus
from engines.execution_reconciliation import (
    ExecutionReconciliationEngine,
    ExecutionReconciliationPolicy,
    ExecutionReconciliationRequest,
    ReconciliationBoundary,
    ReconciliationLifecycleState,
    ReconciliationReasonCode,
    ReconciliationSeverity,
    ReconciliationStatus,
)
from engines.order_management.enums import OrderCommandType, OrderSide, OrderStatus, OrderType
from engines.order_management.models import OrderCommand
from engines.order_management.order_management_engine import OrderManagementEngine
from engines.paper_execution_coordinator import PaperExecutionCoordinator, PaperExecutionRequest, PaperExecutionStatus
from engines.paper_trading.configuration import PaperTradingConfiguration
from engines.paper_trading.engine import PaperTradingEngine
from engines.paper_trading.enums import ManagedPaperSubmissionStatus
from engines.position.enums import PositionSide, PositionStatus, PositionUpdateType
from engines.position.models import PositionState
from engines.position.position_engine import PositionEngine
from engines.risk.enums import RiskDecisionStatus, RiskReasonCode
from engines.risk.models import RiskDecisionRecord
from engines.strategy.enums import TradeDirection
from engines.trade_execution_policy import ExecutionMode, ExecutionPolicy, ExecutionRequest, TradeExecutionPolicyEngine
from engines.trade_execution_policy.enums import ExecutionPlanStatus
from engines.execution_reconciliation.engine import _status_for


IST = ZoneInfo("Asia/Kolkata")
TS = datetime(2026, 7, 20, 9, 30, tzinfo=IST)


def risk_record(**overrides):
    values = {
        "decision_id": "risk-1",
        "timestamp": TS,
        "status": RiskDecisionStatus.APPROVED,
        "approved": True,
        "instrument": "NIFTY",
        "direction": TradeDirection.BULLISH,
        "requested_quantity": 75,
        "approved_quantity": 75,
        "requested_lots": 1,
        "approved_lots": 1,
        "entry_price": 100.0,
        "stop_loss_price": 95.0,
        "target_price": 110.0,
        "risk_per_unit": 5.0,
        "reward_per_unit": 10.0,
        "reward_to_risk": 2.0,
        "requested_trade_risk": 375.0,
        "approved_trade_risk": 375.0,
        "maximum_allowed_trade_risk": 1000.0,
        "estimated_reward": 750.0,
        "capital_at_risk_percentage": 0.5,
        "total_open_risk_after_trade": 375.0,
        "instrument_open_risk_after_trade": 375.0,
        "primary_reason": RiskReasonCode.APPROVED,
        "findings": (),
        "manual_approval_required": False,
        "policy_fingerprint": "risk-policy",
        "plan_fingerprint": "risk-plan",
        "input_fingerprint": "risk-input",
    }
    values.update(overrides)
    return RiskDecisionRecord(**values)


def approved_plan(**overrides):
    values = {
        "instrument": "NIFTY",
        "timestamp": TS + timedelta(seconds=10),
        "risk_decision": risk_record(decision_id=overrides.pop("decision_id", "risk-1")),
        "execution_mode": ExecutionMode.PAPER,
        "requested_order_type": OrderType.LIMIT,
        "requested_entry_price": 100.0,
        "market_reference_price": 100.0,
        "requested_quantity": 75,
        "manual_approval": True,
        "signal_id": overrides.pop("signal_id", "signal-1"),
        "strategy_id": "strategy-1",
        "client_request_id": overrides.pop("client_request_id", "client-1"),
    }
    values.update(overrides)
    request = ExecutionRequest(**values)
    return TradeExecutionPolicyEngine(
        EventBus(),
        instrument=request.instrument,
        timeframe="1m",
        policy=ExecutionPolicy(require_manual_approval=False),
    ).evaluate(request)


def runtime_parts():
    bus = EventBus()
    order = OrderManagementEngine(bus, "NIFTY", "1m")
    paper = PaperTradingEngine(
        bus,
        instrument="NIFTY",
        timeframe="1m",
        safety_mode=RuntimeConfiguration().safety_mode,
        configuration=PaperTradingConfiguration(),
    )
    position = PositionEngine(bus, "NIFTY", "NSE", "1m")
    coordinator = PaperExecutionCoordinator(
        bus,
        instrument="NIFTY",
        timeframe="1m",
        order_management_engine=order,
        paper_trading_engine=paper,
    )
    engine = ExecutionReconciliationEngine(
        bus,
        instrument="NIFTY",
        timeframe="1m",
        order_management_engine=order,
        paper_trading_engine=paper,
        position_engine=position,
        paper_execution_coordinator=coordinator,
    )
    return bus, order, paper, position, coordinator, engine


def paper_request(plan=None, **overrides):
    values = {
        "request_id": overrides.pop("request_id", "paper-request-1"),
        "timestamp": TS + timedelta(seconds=20),
        "instrument": "NIFTY",
        "execution_plan": plan or approved_plan(),
    }
    values.update(overrides)
    return PaperExecutionRequest(**values)


def execute_entry():
    _, order, paper, position, coordinator, engine = runtime_parts()
    engine.start()
    plan = approved_plan()
    receipt = coordinator.execute(paper_request(plan))
    return order, paper, position, coordinator, engine, plan, receipt


def request_for(plan, receipt, **overrides):
    values = {
        "request_id": "reconcile-request-1",
        "timestamp": TS + timedelta(seconds=40),
        "instrument": "NIFTY",
        "execution_plan": plan,
        "execution_receipt": receipt,
    }
    values.update(overrides)
    return ExecutionReconciliationRequest(**values)


def fill_entry(order, coordinator, receipt, quantity=75):
    state = order.apply(OrderCommand(OrderCommandType.ACKNOWLEDGE, receipt.entry_order.order_id, TS + timedelta(seconds=21), broker_order_id="broker-entry"))
    state = order.apply(OrderCommand(OrderCommandType.FILL, receipt.entry_order.order_id, TS + timedelta(seconds=22), fill_quantity=quantity, fill_price=100.0))
    updated = coordinator.on_order_update(state, timestamp=state.updated_at)
    return state, updated


def open_position(quantity=75, symbol="NIFTY", status=PositionStatus.OPEN, side=PositionSide.LONG):
    return PositionState(
        symbol=symbol,
        exchange="NSE",
        timeframe="1m",
        side=side,
        status=status,
        opened_at=TS + timedelta(seconds=22),
        updated_at=TS + timedelta(seconds=22),
        closed_at=None if status is PositionStatus.OPEN else TS + timedelta(seconds=50),
        net_quantity=quantity if side is PositionSide.LONG else -quantity,
        absolute_quantity=quantity,
        average_entry_price=100.0,
        mark_price=100.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        total_pnl=0.0,
        total_buy_quantity=quantity,
        total_sell_quantity=0,
        last_fill_execution_id="fill-entry",
        last_fill_price=100.0,
        last_fill_quantity=quantity,
        last_update_type=PositionUpdateType.OPEN if status is PositionStatus.OPEN else PositionUpdateType.CLOSE,
        version=1,
    )


def reason_codes(report):
    return {finding.reason_code for finding in report.findings}


def test_models_are_immutable_validate_timezone_policy_and_snapshot():
    _, _, _, _, engine, plan, receipt = execute_entry()
    request = request_for(plan, receipt)
    with pytest.raises(FrozenInstanceError):
        request.instrument = "BANKNIFTY"
    with pytest.raises(ValueError):
        ExecutionReconciliationRequest("bad", datetime(2026, 7, 20, 9, 30), "NIFTY", plan, receipt)
    with pytest.raises(TypeError):
        ExecutionReconciliationRequest("bad", TS, "NIFTY", plan, receipt, existing_report_ids=[])
    with pytest.raises(ValueError):
        ExecutionReconciliationPolicy(allowed_instruments=("NIFTY", "NIFTY"))
    snap = engine.snapshot()
    assert snap.lifecycle_state is ReconciliationLifecycleState.READY
    assert snap.broker_order_calls == 0
    assert snap.mutation_calls == 0


def test_start_stop_reset_and_stopped_reconciliation_zero_boundary_reads():
    _, _, _, _, engine, plan, receipt = execute_entry()
    engine.start()
    engine.start()
    assert engine.snapshot().lifecycle_state is ReconciliationLifecycleState.READY
    engine.stop()
    report = engine.reconcile(request_for(plan, receipt))
    assert report.primary_reason is ReconciliationReasonCode.ENGINE_STOPPED
    assert report.order_management_read_count == 0
    assert report.paper_trading_read_count == 0
    assert report.position_read_count == 0
    assert engine.snapshot().lifecycle_state is ReconciliationLifecycleState.STOPPED
    engine.reset_session()
    snap = engine.snapshot()
    assert snap.last_report is None
    assert snap.active_report_ids == ()
    assert snap.order_management_read_count == 0


def test_submitted_entry_reconciles_as_consistent_and_publishes_events():
    bus, _, _, _, _, engine = runtime_parts()
    seen = []
    for name in (events.EXECUTION_RECONCILIATION_STARTED, events.EXECUTION_RECONCILIATION_COMPLETED, events.EXECUTION_RECONCILIATION_STATE_UPDATED):
        bus.subscribe(name, lambda payload, event_name=name: seen.append(event_name))
    engine.start()
    plan = approved_plan()
    receipt = engine._coordinator.execute(paper_request(plan))
    report = engine.reconcile(request_for(plan, receipt))
    assert report.reconciliation_status is ReconciliationStatus.CONSISTENT
    assert report.primary_reason is ReconciliationReasonCode.CONSISTENT
    assert report.entry.order_id == receipt.entry_order.order_id
    assert report.entry.managed_submission_id == receipt.paper_submission_id
    assert report.order_management_read_count > 0
    assert report.paper_trading_read_count > 0
    assert report.position_read_count > 0
    assert engine.snapshot().lifecycle_state is ReconciliationLifecycleState.ACTIVE
    assert events.EXECUTION_RECONCILIATION_STARTED in seen
    assert events.EXECUTION_RECONCILIATION_COMPLETED in seen
    active = engine.reconcile(request_for(plan, receipt, request_id="active-remains-active"))
    assert active.reconciliation_status is ReconciliationStatus.CONSISTENT
    assert engine.snapshot().lifecycle_state is ReconciliationLifecycleState.ACTIVE


def test_full_entry_with_protection_and_position_reconciles_as_consistent():
    order, _, _, coordinator, engine, plan, receipt = execute_entry()
    _, protected = fill_entry(order, coordinator, receipt)
    report = engine.reconcile(request_for(plan, protected, position=open_position()))
    assert report.reconciliation_status is ReconciliationStatus.CONSISTENT
    assert report.stop.order_id == protected.stop_order.order_id
    assert report.target.order_id == protected.target_order.order_id
    assert report.position_quantity == 75


def test_completed_stop_and_target_exits_require_opposite_protection_cancelled():
    order, _, _, coordinator, engine, plan, receipt = execute_entry()
    _, protected = fill_entry(order, coordinator, receipt)
    stop = order.apply(OrderCommand(OrderCommandType.ACKNOWLEDGE, protected.stop_order.order_id, TS + timedelta(seconds=30), broker_order_id="broker-stop"))
    stop = order.apply(OrderCommand(OrderCommandType.FILL, stop.client_order_id, TS + timedelta(seconds=31), fill_quantity=75, fill_price=95.0))
    completed = coordinator.on_order_update(stop, timestamp=stop.updated_at)
    report = engine.reconcile(request_for(plan, completed, position=open_position(quantity=0, status=PositionStatus.CLOSED)))
    assert report.reconciliation_status is ReconciliationStatus.CONSISTENT

    active_target = replace(order.get_order(completed.target_order.order_id), status=OrderStatus.SUBMITTED, filled_quantity=0, remaining_quantity=75)
    report = engine.reconcile(request_for(plan, completed, request_id="broken-opposite", target_order=active_target, position=open_position(quantity=0, status=PositionStatus.CLOSED)))
    assert ReconciliationReasonCode.OPPOSITE_PROTECTION_NOT_CANCELLED in reason_codes(report)


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (lambda plan, receipt: (replace(plan, instrument="BANKNIFTY"), receipt), ReconciliationReasonCode.INSTRUMENT_MISMATCH),
        (lambda plan, receipt: (plan, replace(receipt, instrument="BANKNIFTY")), ReconciliationReasonCode.INSTRUMENT_MISMATCH),
        (lambda plan, receipt: (plan, replace(receipt, execution_plan_id="other-plan")), ReconciliationReasonCode.EXECUTION_PLAN_ID_MISMATCH),
        (lambda plan, receipt: (plan, replace(receipt, execution_plan_fingerprint="other-fingerprint")), ReconciliationReasonCode.EXECUTION_PLAN_FINGERPRINT_MISMATCH),
        (lambda plan, receipt: (plan, replace(receipt, risk_decision_id="other-risk")), ReconciliationReasonCode.EXECUTION_PLAN_ID_MISMATCH),
        (lambda plan, receipt: (plan, replace(receipt, entry_order=replace(receipt.entry_order, order_id=receipt.stop_order.order_id if receipt.stop_order else receipt.entry_order.order_id))), ReconciliationReasonCode.DUPLICATE_ORDER_IDENTITY),
    ],
)
def test_identity_mismatches_are_detected(mutator, reason):
    order, _, _, coordinator, engine, plan, receipt = execute_entry()
    _, protected = fill_entry(order, coordinator, receipt)
    changed_plan, changed_receipt = mutator(plan, protected)
    report = engine.reconcile(request_for(changed_plan, changed_receipt, request_id=f"identity-{reason.value}"))
    assert reason in reason_codes(report)
    assert report.broker_order_calls == 0
    assert report.mutation_calls == 0


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("side", OrderSide.SELL, ReconciliationReasonCode.ORDER_SIDE_MISMATCH),
        ("order_type", OrderType.MARKET, ReconciliationReasonCode.ORDER_TYPE_MISMATCH),
        ("quantity", 50, ReconciliationReasonCode.ORDER_QUANTITY_MISMATCH),
        ("limit_price", 101.0, ReconciliationReasonCode.ORDER_LIMIT_PRICE_MISMATCH),
        ("trigger_price", 99.0, ReconciliationReasonCode.ORDER_TRIGGER_PRICE_MISMATCH),
        ("filled_quantity", 100, ReconciliationReasonCode.INVALID_ORDER_STATE),
        ("remaining_quantity", 99, ReconciliationReasonCode.REMAINING_QUANTITY_MISMATCH),
    ],
)
def test_entry_order_mismatches_are_detected(field, value, reason):
    _, _, _, _, engine, plan, receipt = execute_entry()
    order = engine._order_engine.get_order(receipt.entry_order.order_id)
    changed = replace(order, **{field: value})
    report = engine.reconcile(request_for(plan, receipt, request_id=f"entry-{field}", entry_order=changed))
    assert reason in reason_codes(report)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("purpose", "target", ReconciliationReasonCode.ORDER_PURPOSE_MISMATCH),
        ("instrument", "BANKNIFTY", ReconciliationReasonCode.INSTRUMENT_MISMATCH),
        ("status", ManagedPaperSubmissionStatus.FILLED, ReconciliationReasonCode.TERMINAL_STATE_REGRESSION),
        ("filled_quantity", 10, ReconciliationReasonCode.FILLED_QUANTITY_MISMATCH),
        ("order_id", "unknown-order", ReconciliationReasonCode.ORPHANED_MANAGED_SUBMISSION),
        ("execution_plan_id", "other-plan", ReconciliationReasonCode.EXECUTION_PLAN_ID_MISMATCH),
    ],
)
def test_managed_submission_mismatches_are_detected(field, value, reason):
    _, paper, _, _, engine, plan, receipt = execute_entry()
    submission = paper.managed_submission(receipt.paper_submission_id)
    changed = replace(submission, **{field: value})
    report = engine.reconcile(request_for(plan, receipt, request_id=f"managed-{field}", entry_managed_submission=changed))
    assert reason in reason_codes(report)


@pytest.mark.parametrize(
    ("label", "mutator", "reason"),
    [
        ("missing-stop", lambda protected: replace(protected, stop_order=None, stop_paper_submission_id=None), ReconciliationReasonCode.MISSING_STOP_PROTECTION),
        ("missing-target", lambda protected: replace(protected, target_order=None, target_paper_submission_id=None), ReconciliationReasonCode.MISSING_TARGET_PROTECTION),
        ("stop-side", lambda protected: replace(protected, stop_order=replace(protected.stop_order, side=OrderSide.BUY)), ReconciliationReasonCode.ORDER_SIDE_MISMATCH),
        ("target-side", lambda protected: replace(protected, target_order=replace(protected.target_order, side=OrderSide.BUY)), ReconciliationReasonCode.ORDER_SIDE_MISMATCH),
        ("stop-quantity", lambda protected: replace(protected, stop_order=replace(protected.stop_order, quantity=50)), ReconciliationReasonCode.PROTECTIVE_QUANTITY_MISMATCH),
        ("stop-reduce", lambda protected: replace(protected, stop_order=replace(protected.stop_order, reduce_only=False)), ReconciliationReasonCode.PROTECTIVE_REDUCE_ONLY_MISMATCH),
    ],
)
def test_protective_order_mismatches_are_detected(label, mutator, reason):
    order, _, _, coordinator, engine, plan, receipt = execute_entry()
    _, protected = fill_entry(order, coordinator, receipt)
    changed = mutator(protected)
    report = engine.reconcile(request_for(plan, changed, request_id=f"protective-{label}", position=open_position()))
    assert reason in reason_codes(report)


def test_protection_before_full_entry_fill_and_missing_position_are_detected():
    order, _, _, coordinator, engine, plan, receipt = execute_entry()
    _, protected = fill_entry(order, coordinator, receipt)
    partial_entry = replace(order.get_order(protected.entry_order.order_id), filled_quantity=25, remaining_quantity=50, status=OrderStatus.PARTIALLY_FILLED)
    report = engine.reconcile(request_for(plan, protected, request_id="premature-protection", entry_order=partial_entry))
    assert ReconciliationReasonCode.PROTECTION_CREATED_BEFORE_ENTRY_FILL in reason_codes(report)
    report = engine.reconcile(request_for(plan, protected, request_id="missing-position"))
    assert ReconciliationReasonCode.FILLED_ENTRY_WITHOUT_POSITION in reason_codes(report)


@pytest.mark.parametrize(
    ("receipt_status", "entry_status", "stop_status", "target_status", "position", "reason"),
    [
        (PaperExecutionStatus.CANCELLED, OrderStatus.SUBMITTED, None, None, None, ReconciliationReasonCode.CANCELLED_RECEIPT_HAS_ACTIVE_ORDER),
        (PaperExecutionStatus.COMPLETED, OrderStatus.FILLED, OrderStatus.FILLED, OrderStatus.SUBMITTED, open_position(quantity=0, status=PositionStatus.CLOSED), ReconciliationReasonCode.OPPOSITE_PROTECTION_NOT_CANCELLED),
        (PaperExecutionStatus.COMPLETED, OrderStatus.FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED, open_position(), ReconciliationReasonCode.COMPLETED_RECEIPT_HAS_OPEN_POSITION),
        (PaperExecutionStatus.ACTIVE, OrderStatus.FILLED, OrderStatus.SUBMITTED, OrderStatus.SUBMITTED, open_position(quantity=0, status=PositionStatus.CLOSED), ReconciliationReasonCode.ACTIVE_RECEIPT_HAS_CLOSED_POSITION),
        (PaperExecutionStatus.ACTIVE, OrderStatus.FILLED, OrderStatus.SUBMITTED, OrderStatus.SUBMITTED, open_position(quantity=50), ReconciliationReasonCode.POSITION_QUANTITY_MISMATCH),
        (PaperExecutionStatus.ACTIVE, OrderStatus.FILLED, OrderStatus.SUBMITTED, OrderStatus.SUBMITTED, open_position(symbol="BANKNIFTY"), ReconciliationReasonCode.POSITION_INSTRUMENT_MISMATCH),
    ],
)
def test_terminal_and_position_invariants_are_detected(receipt_status, entry_status, stop_status, target_status, position, reason):
    order, _, _, coordinator, engine, plan, receipt = execute_entry()
    _, protected = fill_entry(order, coordinator, receipt)
    changed = replace(protected, status=receipt_status)
    entry = replace(order.get_order(changed.entry_order.order_id), status=entry_status, filled_quantity=75 if entry_status is OrderStatus.FILLED else 0, remaining_quantity=0 if entry_status is OrderStatus.FILLED else 75)
    stop = order.get_order(changed.stop_order.order_id)
    target = order.get_order(changed.target_order.order_id)
    if stop_status is not None:
        stop = replace(stop, status=stop_status, filled_quantity=75 if stop_status is OrderStatus.FILLED else 0, remaining_quantity=0 if stop_status is OrderStatus.FILLED else 75)
    if target_status is not None:
        target = replace(target, status=target_status, filled_quantity=75 if target_status is OrderStatus.FILLED else 0, remaining_quantity=0 if target_status is OrderStatus.FILLED else 75)
    report = engine.reconcile(request_for(plan, changed, request_id=f"terminal-{reason.value}", entry_order=entry, stop_order=stop, target_order=target, position=position))
    assert reason in reason_codes(report)


def test_idempotency_same_input_same_report_changed_request_rejected_and_ordering_deterministic():
    _, _, _, _, engine, plan, receipt = execute_entry()
    request = request_for(plan, receipt)
    first = engine.reconcile(request)
    reads = (engine.snapshot().order_management_read_count, engine.snapshot().paper_trading_read_count, engine.snapshot().position_read_count)
    second = engine.reconcile(request)
    assert second is first
    assert (engine.snapshot().order_management_read_count, engine.snapshot().paper_trading_read_count, engine.snapshot().position_read_count) == reads
    conflict = engine.reconcile(request_for(plan, receipt, request_id=request.request_id, correlation_id="changed"))
    assert conflict.primary_reason is ReconciliationReasonCode.INVALID_REQUEST
    broken = replace(receipt, execution_plan_fingerprint="x", instrument="BANKNIFTY")
    report_a = engine.reconcile(request_for(plan, broken, request_id="ordering-a"))
    report_b = engine.reconcile(request_for(plan, broken, request_id="ordering-b"))
    assert [finding.finding_id for finding in report_a.findings] == [finding.finding_id for finding in report_b.findings]
    assert report_a.primary_reason is report_b.primary_reason


def test_expected_inconsistencies_do_not_fail_lifecycle_and_valid_reconciliation_recovers():
    _, _, _, _, engine, plan, receipt = execute_entry()
    missing = replace(receipt, entry_order=replace(receipt.entry_order, order_id="missing-order"))
    report = engine.reconcile(request_for(plan, missing, request_id="missing-order"))
    assert report.reconciliation_status is ReconciliationStatus.INCONSISTENT
    assert engine.snapshot().lifecycle_state is ReconciliationLifecycleState.ACTIVE
    ok = engine.reconcile(request_for(plan, receipt, request_id="after-missing"))
    assert ok.reconciliation_status is ReconciliationStatus.CONSISTENT


def test_unexpected_internal_failure_produces_failed_report_with_zero_mutation_and_broker_calls():
    _, _, _, _, engine, plan, receipt = execute_entry()

    def boom(_order_id):
        raise RuntimeError("read failure")

    engine._order_engine.get_order = boom
    report = engine.reconcile(request_for(plan, receipt))
    assert report.reconciliation_status is ReconciliationStatus.FAILED
    assert report.primary_reason is ReconciliationReasonCode.INTERNAL_RECONCILIATION_ERROR
    assert report.broker_order_calls == 0
    assert report.mutation_calls == 0
    assert engine.snapshot().lifecycle_state is ReconciliationLifecycleState.FAILED


def test_one_runtime_inconsistency_does_not_affect_another_runtime():
    bad = execute_entry()
    good = execute_entry()
    bad_report = bad[4].reconcile(request_for(bad[5], replace(bad[6], entry_order=replace(bad[6].entry_order, order_id="missing")), request_id="bad-runtime"))
    good_report = good[4].reconcile(request_for(good[5], good[6], request_id="good-runtime"))
    assert bad_report.reconciliation_status is ReconciliationStatus.INCONSISTENT
    assert good_report.reconciliation_status is ReconciliationStatus.CONSISTENT


def test_missing_receipt_report_is_finalized_stored_published_and_zero_read():
    bus, _, _, _, _, engine = runtime_parts()
    seen = []
    for name in (events.EXECUTION_RECONCILIATION_COMPLETED, events.EXECUTION_RECONCILIATION_INCONSISTENT, events.EXECUTION_RECONCILIATION_STATE_UPDATED):
        bus.subscribe(name, lambda payload, event_name=name: seen.append(event_name))
    engine.start()
    before = engine.snapshot()
    report = engine.reconcile_receipt("missing-receipt", timestamp=TS + timedelta(minutes=1))
    snap = engine.snapshot()
    assert engine.get_report(report.report_id) == report
    assert engine.get_report_for_request(f"reconcile-receipt:missing-receipt:{(TS + timedelta(minutes=1)).isoformat()}") == report
    assert snap.last_report == report
    assert snap.reconciliation_count == before.reconciliation_count + 1
    assert snap.incomplete_count == before.incomplete_count + 1
    assert report.reconciliation_status is ReconciliationStatus.INCOMPLETE
    assert report.order_management_read_count == 0
    assert report.paper_trading_read_count == 0
    assert report.position_read_count == 0
    assert report.mutation_calls == 0
    assert report.broker_order_calls == 0
    assert events.EXECUTION_RECONCILIATION_COMPLETED in seen
    assert events.EXECUTION_RECONCILIATION_INCONSISTENT in seen
    assert events.EXECUTION_RECONCILIATION_STATE_UPDATED in seen


def test_missing_plan_report_is_finalized_stored_and_published():
    bus, _, _, _, coordinator, engine = runtime_parts()
    seen = []
    bus.subscribe(events.EXECUTION_RECONCILIATION_COMPLETED, lambda payload: seen.append(payload.report_id))
    engine.start()
    plan = approved_plan()
    receipt = coordinator.execute(paper_request(plan))
    coordinator._latest_plan_by_receipt.clear()
    report = engine.reconcile_receipt(receipt.receipt_id, timestamp=TS + timedelta(minutes=2))
    assert engine.get_report(report.report_id) == report
    assert engine.snapshot().last_report == report
    assert report.reconciliation_status is ReconciliationStatus.INCOMPLETE
    assert report.primary_reason is ReconciliationReasonCode.INVALID_EXECUTION_PLAN
    assert seen == [report.report_id]


def test_blocked_reports_are_finalized_published_stored_and_zero_read():
    bus, _, _, _, _, engine = runtime_parts()
    plan = approved_plan()
    receipt = engine._coordinator.execute(paper_request(plan))
    seen = []
    for name in (events.EXECUTION_RECONCILIATION_COMPLETED, events.EXECUTION_RECONCILIATION_INVALID, events.EXECUTION_RECONCILIATION_STATE_UPDATED):
        bus.subscribe(name, lambda payload, event_name=name: seen.append(event_name))
    engine.start()
    engine.stop()
    stopped = engine.reconcile(request_for(plan, receipt, request_id="stopped-finalized"))
    assert engine.get_report(stopped.report_id) == stopped
    assert engine.snapshot().last_report == stopped
    assert stopped.order_management_read_count == stopped.paper_trading_read_count == stopped.position_read_count == 0
    assert stopped.mutation_calls == 0
    assert stopped.broker_order_calls == 0
    assert stopped.reconciliation_status is ReconciliationStatus.INVALID
    assert stopped.primary_reason is ReconciliationReasonCode.ENGINE_STOPPED
    assert engine.snapshot().lifecycle_state is ReconciliationLifecycleState.STOPPED
    assert events.EXECUTION_RECONCILIATION_INVALID in seen
    stopped_events = len(seen)
    stopped_retry = engine.reconcile(request_for(plan, receipt, request_id="stopped-finalized"))
    assert stopped_retry is stopped
    assert len(seen) == stopped_events
    second_stopped = engine.reconcile(request_for(plan, receipt, request_id="stopped-again"))
    assert second_stopped.primary_reason is ReconciliationReasonCode.ENGINE_STOPPED
    assert second_stopped.order_management_read_count == second_stopped.paper_trading_read_count == second_stopped.position_read_count == 0
    assert second_stopped.mutation_calls == 0
    assert second_stopped.broker_order_calls == 0
    assert engine.snapshot().lifecycle_state is ReconciliationLifecycleState.STOPPED

    _, _, _, _, _, locked_engine = runtime_parts()
    locked_engine.start()
    locked_engine._state = ReconciliationLifecycleState.LOCKED
    locked = locked_engine.reconcile(request_for(plan, receipt, request_id="locked-finalized"))
    assert locked_engine.get_report(locked.report_id) == locked
    assert locked.order_management_read_count == locked.paper_trading_read_count == locked.position_read_count == 0
    assert locked.mutation_calls == 0
    assert locked.broker_order_calls == 0
    assert locked.primary_reason is ReconciliationReasonCode.ENGINE_LOCKED
    assert locked_engine.snapshot().lifecycle_state is ReconciliationLifecycleState.LOCKED
    locked_retry = locked_engine.reconcile(request_for(plan, receipt, request_id="locked-finalized"))
    assert locked_retry is locked
    second_locked = locked_engine.reconcile(request_for(plan, receipt, request_id="locked-again"))
    assert second_locked.primary_reason is ReconciliationReasonCode.ENGINE_LOCKED
    assert second_locked.order_management_read_count == second_locked.paper_trading_read_count == second_locked.position_read_count == 0
    assert second_locked.mutation_calls == 0
    assert second_locked.broker_order_calls == 0
    assert locked_engine.snapshot().lifecycle_state is ReconciliationLifecycleState.LOCKED

    _, _, _, _, _, disabled_engine = runtime_parts()
    disabled = disabled_engine.reconcile(request_for(plan, receipt, request_id="disabled-finalized"), policy=ExecutionReconciliationPolicy(enabled=False))
    assert disabled_engine.get_report(disabled.report_id) == disabled
    assert disabled.order_management_read_count == disabled.paper_trading_read_count == disabled.position_read_count == 0
    assert disabled_engine.snapshot().lifecycle_state is ReconciliationLifecycleState.ACTIVE

    _, _, _, _, _, stopped_disabled_engine = runtime_parts()
    stopped_disabled_engine.start()
    stopped_disabled_engine.stop()
    stopped_disabled = stopped_disabled_engine.reconcile(request_for(plan, receipt, request_id="stopped-disabled"), policy=ExecutionReconciliationPolicy(enabled=False))
    assert stopped_disabled.primary_reason is ReconciliationReasonCode.ENGINE_STOPPED
    assert stopped_disabled.order_management_read_count == stopped_disabled.paper_trading_read_count == stopped_disabled.position_read_count == 0
    assert stopped_disabled_engine.snapshot().lifecycle_state is ReconciliationLifecycleState.STOPPED

    _, _, _, _, _, locked_disabled_engine = runtime_parts()
    locked_disabled_engine.start()
    locked_disabled_engine._state = ReconciliationLifecycleState.LOCKED
    locked_disabled = locked_disabled_engine.reconcile(request_for(plan, receipt, request_id="locked-disabled"), policy=ExecutionReconciliationPolicy(enabled=False))
    assert locked_disabled.primary_reason is ReconciliationReasonCode.ENGINE_LOCKED
    assert locked_disabled.order_management_read_count == locked_disabled.paper_trading_read_count == locked_disabled.position_read_count == 0
    assert locked_disabled_engine.snapshot().lifecycle_state is ReconciliationLifecycleState.LOCKED


def test_status_precedence_for_contradictions_missing_state_warnings_and_failure():
    _, _, _, _, engine, plan, receipt = execute_entry()
    fingerprint = engine.reconcile(request_for(plan, replace(receipt, execution_plan_fingerprint="x"), request_id="fp-only"))
    assert fingerprint.reconciliation_status is ReconciliationStatus.INCONSISTENT
    both = engine.reconcile(request_for(plan, replace(receipt, execution_plan_fingerprint="x", entry_order=replace(receipt.entry_order, order_id="missing")), request_id="fp-missing"))
    assert both.reconciliation_status is ReconciliationStatus.INCONSISTENT
    plan_id = engine.reconcile(request_for(plan, replace(receipt, execution_plan_id="other", paper_submission_id="missing-submission"), request_id="planid-missing"))
    assert plan_id.reconciliation_status is ReconciliationStatus.INCONSISTENT

    _, _, _, _, _, empty_engine = runtime_parts()
    missing_only = empty_engine.reconcile(request_for(plan, replace(receipt, entry_order=None, paper_submission_id=None), request_id="pure-missing-entry"))
    assert missing_only.reconciliation_status is ReconciliationStatus.INCOMPLETE
    missing_submission = engine.reconcile(request_for(plan, replace(receipt, paper_submission_id="missing-submission"), request_id="pure-missing-submission"))
    assert missing_submission.reconciliation_status is ReconciliationStatus.INCOMPLETE

    warning = engine._finding(TS, ReconciliationSeverity.WARNING, ReconciliationReasonCode.CONSISTENT, "warning only", ReconciliationBoundary.CROSS_BOUNDARY)
    assert _status_for((warning,)) is ReconciliationStatus.CONSISTENT_WITH_WARNINGS


def test_report_read_counts_are_per_operation_and_snapshot_counts_are_cumulative():
    _, _, _, _, engine, plan, receipt = execute_entry()
    first = engine.reconcile(request_for(plan, receipt, request_id="read-one"))
    assert first.order_management_read_count == 2
    assert first.paper_trading_read_count == 2
    assert first.position_read_count == 1
    snap_after_first = engine.snapshot()
    second = engine.reconcile(request_for(plan, receipt, request_id="read-two", entry_order=engine._order_engine.get_order(receipt.entry_order.order_id), entry_managed_submission=engine._paper_engine.managed_submission(receipt.paper_submission_id), position=None))
    assert second is first
    assert second.order_management_read_count == 2
    assert second.paper_trading_read_count == 2
    assert second.position_read_count == 1
    snap_after_second = engine.snapshot()
    assert snap_after_second.order_management_read_count > snap_after_first.order_management_read_count
    assert snap_after_second.paper_trading_read_count > snap_after_first.paper_trading_read_count
    assert snap_after_second.position_read_count > snap_after_first.position_read_count


def test_idempotency_finalization_retry_conflict_and_same_state_reuse():
    bus, _, _, _, _, engine = runtime_parts()
    completion_events = []
    bus.subscribe(events.EXECUTION_RECONCILIATION_COMPLETED, lambda payload: completion_events.append(payload.report_id))
    engine.start()
    plan = approved_plan()
    receipt = engine._coordinator.execute(paper_request(plan))
    request = request_for(plan, receipt, request_id="idem")
    first = engine.reconcile(request)
    count = engine.snapshot().reconciliation_count
    findings_count = len(engine.snapshot().findings)
    reads = (engine.snapshot().order_management_read_count, engine.snapshot().paper_trading_read_count, engine.snapshot().position_read_count)
    events_count = len(completion_events)
    retry = engine.reconcile(request)
    assert retry is first
    assert engine.snapshot().reconciliation_count == count
    assert len(engine.snapshot().findings) == findings_count
    assert (engine.snapshot().order_management_read_count, engine.snapshot().paper_trading_read_count, engine.snapshot().position_read_count) == reads
    assert len(completion_events) == events_count

    conflict = engine.reconcile(request_for(plan, receipt, request_id="idem", correlation_id="changed"))
    assert conflict.reconciliation_status is ReconciliationStatus.INVALID
    assert engine.get_report_for_request("idem") is first
    conflict_count = engine.snapshot().reconciliation_count
    conflict_retry = engine.reconcile(request_for(plan, receipt, request_id="idem", correlation_id="changed"))
    assert conflict_retry is conflict
    assert engine.snapshot().reconciliation_count == conflict_count

    same_state = engine.reconcile(request_for(plan, receipt, request_id="same-state"))
    assert same_state is first
    assert same_state.input_fingerprint == first.input_fingerprint
    assert engine.snapshot().reconciliation_count == conflict_count


def test_report_lookup_is_read_only_and_silent():
    bus, _, _, _, _, engine = runtime_parts()
    seen = []
    bus.subscribe(events.EXECUTION_RECONCILIATION_COMPLETED, lambda payload: seen.append(payload.report_id))
    engine.start()
    plan = approved_plan()
    receipt = engine._coordinator.execute(paper_request(plan))
    report = engine.reconcile(request_for(plan, receipt, request_id="lookup"))
    reads = (engine.snapshot().order_management_read_count, engine.snapshot().paper_trading_read_count, engine.snapshot().position_read_count)
    events_count = len(seen)
    assert engine.get_report(report.report_id) is report
    assert engine.get_report_for_request("lookup") is report
    assert engine.get_report("unknown") is None
    assert engine.get_report_for_request("unknown") is None
    assert (engine.snapshot().order_management_read_count, engine.snapshot().paper_trading_read_count, engine.snapshot().position_read_count) == reads
    assert len(seen) == events_count


def test_runtime_and_orchestrator_expose_explicit_reconciliation_without_autonomous_loop():
    app = ApplicationOrchestrator(EventBus(), RuntimeConfiguration())
    app.start()
    runtime = app.get_runtime(RuntimeInstrument.NIFTY)
    plan = approved_plan()
    receipt = app.execute_paper_plan(RuntimeInstrument.NIFTY, paper_request(plan))
    before = app.snapshot().runtime_snapshots[0].execution_reconciliation.reconciliation_count
    assert before == 0
    report = app.reconcile_paper_execution(RuntimeInstrument.NIFTY, request_for(plan, receipt))
    assert report.reconciliation_status is ReconciliationStatus.CONSISTENT
    assert app.snapshot().runtime_snapshots[0].execution_reconciliation.last_report == report
    by_receipt = runtime.reconcile_paper_execution_receipt(receipt.receipt_id, timestamp=TS + timedelta(seconds=45))
    assert by_receipt.receipt_id == receipt.receipt_id


def test_read_only_spies_prove_mutation_methods_are_never_called():
    _, _, _, _, engine, plan, receipt = execute_entry()
    calls = {"order_create": 0, "order_apply": 0, "paper_submit": 0, "paper_update": 0, "paper_cancel": 0, "position_fill": 0, "position_mark": 0}

    def mark(name):
        def inner(*args, **kwargs):
            calls[name] += 1
            raise AssertionError(name)
        return inner

    engine._order_engine.create = mark("order_create")
    engine._order_engine.apply = mark("order_apply")
    engine._paper_engine.submit_managed_order = mark("paper_submit")
    engine._paper_engine.update_managed_order = mark("paper_update")
    engine._paper_engine.cancel_managed_order = mark("paper_cancel")
    engine._position_engine.apply_fill = mark("position_fill")
    engine._position_engine.apply_mark = mark("position_mark")
    report = engine.reconcile(request_for(plan, receipt))
    assert report.reconciliation_status is ReconciliationStatus.CONSISTENT
    assert calls == {key: 0 for key in calls}
    assert report.broker_order_calls == 0
    assert report.mutation_calls == 0


def test_no_second_event_bus_threads_async_sleep_or_broker_calls_in_reconciliation_package():
    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("engines/execution_reconciliation").glob("*.py"))
    for forbidden in (
        "EventBus(",
        "threading",
        "asyncio",
        "time.sleep",
        "place_order",
        "modify_order",
        "broker_adapter",
        "kite",
        "zerodha",
        "clear_persistent_data=True",
        "submit_managed_order(",
        "update_managed_order(",
        "cancel_managed_order(",
    ):
        assert forbidden not in text


def test_finding_fields_and_boundaries_are_stable_for_publication():
    _, _, _, _, engine, plan, receipt = execute_entry()
    broken = replace(receipt, execution_plan_fingerprint="x")
    report = engine.reconcile(request_for(plan, broken))
    finding = report.findings[0]
    assert finding.severity is ReconciliationSeverity.CRITICAL
    assert finding.boundary in {ReconciliationBoundary.CROSS_BOUNDARY, ReconciliationBoundary.COORDINATOR_RECEIPT}
    assert finding.finding_id
    assert finding.occurrence_count == 1
