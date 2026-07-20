from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from core.event_bus import EventBus
from core import events
from engines.order_management.enums import OrderCommandType, OrderSide, OrderStatus, OrderType
from engines.order_management.models import OrderCommand
from engines.order_management.order_management_engine import OrderManagementEngine
from engines.paper_execution_coordinator import (
    CoordinatorLifecycleState,
    PaperExecutionCoordinator,
    PaperExecutionCoordinatorPolicy,
    PaperExecutionDecision,
    PaperExecutionReasonCode,
    PaperExecutionRequest,
    PaperExecutionStatus,
)
from engines.paper_trading.configuration import PaperTradingConfiguration
from engines.paper_trading.engine import PaperTradingEngine
from engines.risk.enums import RiskDecisionStatus, RiskReasonCode
from engines.risk.models import RiskDecisionRecord
from engines.strategy.enums import TradeDirection
from engines.trade_execution_policy import ExecutionMode, ExecutionPolicy, ExecutionRequest, TradeExecutionPolicyEngine
from engines.trade_execution_policy.enums import ExecutionPlanStatus, ExecutionRoutingTarget


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
    return TradeExecutionPolicyEngine(EventBus(), instrument=request.instrument, timeframe="1m", policy=ExecutionPolicy(require_manual_approval=False)).evaluate(request)


def coordinator(*, bus=None, paper=None):
    event_bus = bus or EventBus()
    paper_engine = paper or PaperTradingEngine(event_bus, instrument="NIFTY", timeframe="1m", safety_mode=RuntimeConfiguration().safety_mode, configuration=PaperTradingConfiguration())
    return PaperExecutionCoordinator(
        event_bus,
        instrument="NIFTY",
        timeframe="1m",
        order_management_engine=OrderManagementEngine(event_bus, "NIFTY", "1m"),
        paper_trading_engine=paper_engine,
    )


def execution_request(plan=None, **overrides):
    values = {
        "request_id": "paper-request-1",
        "timestamp": TS + timedelta(seconds=20),
        "instrument": "NIFTY",
        "execution_plan": plan or approved_plan(),
        "existing_execution_receipt_ids": (),
    }
    values.update(overrides)
    return PaperExecutionRequest(**values)


def plan_with_mode(value):
    plan = approved_plan()
    object.__setattr__(plan, "execution_mode", value)
    return plan


def unsafe_plan(**fields):
    plan = approved_plan()
    for name, value in fields.items():
        object.__setattr__(plan, name, value)
    return plan


def test_models_are_immutable_and_validate_required_inputs():
    request = execution_request()
    assert request.instrument == "NIFTY"
    with pytest.raises(FrozenInstanceError):
        request.instrument = "BANKNIFTY"
    with pytest.raises(ValueError):
        PaperExecutionRequest("", TS, "NIFTY", approved_plan())
    with pytest.raises(ValueError):
        PaperExecutionRequest("x", datetime(2026, 7, 20, 9, 30), "NIFTY", approved_plan())
    with pytest.raises(ValueError):
        PaperExecutionCoordinatorPolicy(allowed_instruments=("NIFTY", "NIFTY"))


def test_lifecycle_start_stop_and_reset_clear_only_coordinator_state():
    item = coordinator()
    assert item.snapshot().lifecycle_state is CoordinatorLifecycleState.CREATED
    item.start()
    item.start()
    assert item.snapshot().lifecycle_state is CoordinatorLifecycleState.READY
    receipt = item.execute(execution_request())
    assert receipt.status is PaperExecutionStatus.ENTRY_SUBMITTED
    assert item.snapshot().order_management_request_count == 1
    item.reset_session()
    snap = item.snapshot()
    assert snap.active_receipt_ids == ()
    assert snap.order_management_request_count == 1
    item.stop()
    stopped = item.execute(execution_request(approved_plan(decision_id="risk-stop", client_request_id="client-stop", signal_id="signal-stop"), request_id="stopped"))
    assert stopped.primary_reason is PaperExecutionReasonCode.COORDINATOR_STOPPED
    assert stopped.order_management_request_count == 0
    assert stopped.paper_submission_count == 0


@pytest.mark.parametrize(
    ("plan_factory", "reason"),
    [
        (lambda: approved_plan(execution_mode=ExecutionMode.PLAN_ONLY), PaperExecutionReasonCode.UNSUPPORTED_ROUTING_TARGET),
        (lambda: plan_with_mode("live"), PaperExecutionReasonCode.UNSUPPORTED_EXECUTION_MODE),
        (lambda: replace(approved_plan(), routing_target=ExecutionRoutingTarget.PLAN_ONLY), PaperExecutionReasonCode.UNSUPPORTED_ROUTING_TARGET),
        (lambda: replace(approved_plan(), status=ExecutionPlanStatus.PREPARED), PaperExecutionReasonCode.PLAN_NOT_READY_FOR_PAPER),
        (lambda: TradeExecutionPolicyEngine(EventBus(), instrument="NIFTY", timeframe="1m").evaluate(ExecutionRequest(instrument="NIFTY", timestamp=TS, risk_decision=risk_record(decision_id="await"), execution_mode=ExecutionMode.PAPER, requested_order_type=OrderType.LIMIT, requested_entry_price=100.0, market_reference_price=100.0, requested_quantity=75, manual_approval=False)), PaperExecutionReasonCode.PLAN_NOT_READY_FOR_PAPER),
        (lambda: unsafe_plan(broker_submission_allowed=True), PaperExecutionReasonCode.BROKER_SUBMISSION_BLOCKED),
        (lambda: unsafe_plan(broker_order_calls=1), PaperExecutionReasonCode.BROKER_SUBMISSION_BLOCKED),
    ],
)
def test_ineligible_plans_fail_closed_without_downstream_calls(plan_factory, reason):
    receipt = coordinator().execute(execution_request(plan_factory()))
    assert receipt.primary_reason is reason
    assert receipt.decision is not PaperExecutionDecision.APPROVED
    assert receipt.order_management_request_count == 0
    assert receipt.paper_submission_count == 0
    assert receipt.broker_order_calls == 0


def test_expired_wrong_instrument_and_invalid_protective_plan_are_rejected_without_failed_lifecycle():
    item = coordinator()
    expired = item.execute(execution_request(timestamp=TS + timedelta(minutes=10)))
    assert expired.primary_reason is PaperExecutionReasonCode.PLAN_EXPIRED
    wrong = item.execute(execution_request(replace(approved_plan(), instrument="BANKNIFTY"), request_id="wrong"))
    assert wrong.primary_reason is PaperExecutionReasonCode.PLAN_INSTRUMENT_MISMATCH
    plan = approved_plan(decision_id="bad-protective", client_request_id="bad-protective", signal_id="bad-protective")
    invalid_stop = replace(plan.stop_plan, side=plan.entry_side)
    invalid = item.execute(execution_request(replace(plan, stop_plan=invalid_stop), request_id="invalid-protective"))
    assert invalid.primary_reason is PaperExecutionReasonCode.INVALID_PROTECTIVE_PLAN
    assert item.snapshot().lifecycle_state is CoordinatorLifecycleState.READY


def test_valid_ready_for_paper_plan_creates_one_order_and_one_paper_submission_preserving_entry_fields():
    item = coordinator()
    plan = approved_plan()
    receipt = item.execute(execution_request(plan))
    assert receipt.decision is PaperExecutionDecision.APPROVED
    assert receipt.status is PaperExecutionStatus.ENTRY_SUBMITTED
    assert receipt.entry_order.order_id == f"paper-entry:{plan.execution_plan_id}"
    assert receipt.entry_order.side is plan.entry_side
    assert receipt.entry_order.order_type is plan.entry_order_type
    assert receipt.entry_order.quantity == plan.entry_quantity
    assert receipt.entry_order.limit_price == plan.entry_limit_price
    assert receipt.entry_order.trigger_price == plan.entry_trigger_price
    assert receipt.paper_submission_id == f"paper-submission:entry:{receipt.entry_order.order_id}"
    assert receipt.order_management_request_count == 1
    assert receipt.paper_submission_count == 1
    assert item.snapshot().broker_order_calls == 0


def test_exact_retry_is_idempotent_and_conflicting_duplicates_are_rejected():
    item = coordinator()
    plan = approved_plan()
    request = execution_request(plan)
    first = item.execute(request)
    second = item.execute(request)
    assert first is second
    assert item.snapshot().order_management_request_count == 1
    assert item.snapshot().paper_submission_count == 1
    conflicting_request = item.execute(execution_request(plan, request_id=request.request_id, correlation_id="different"))
    assert conflicting_request.primary_reason is PaperExecutionReasonCode.DUPLICATE_EXECUTION
    changed_plan = replace(plan, input_fingerprint="changed")
    conflicting_plan = item.execute(execution_request(changed_plan, request_id="changed-plan"))
    assert conflicting_plan.primary_reason is PaperExecutionReasonCode.DUPLICATE_EXECUTION
    assert item.snapshot().active_receipt_ids == (first.receipt_id,)


def test_entry_fill_updates_create_protective_orders_once_and_preserve_approved_prices():
    item = coordinator()
    plan = approved_plan()
    receipt = item.execute(execution_request(plan))
    item._order_engine.apply(OrderCommand(OrderCommandType.ACKNOWLEDGE, receipt.entry_order.order_id, TS + timedelta(seconds=20), broker_order_id="broker-entry"))
    partial = item._order_engine.apply(OrderCommand(OrderCommandType.FILL, receipt.entry_order.order_id, TS + timedelta(seconds=21), fill_quantity=25, fill_price=100.0))
    partial_receipt = item.on_order_update(partial, timestamp=partial.updated_at)
    assert partial_receipt.status is PaperExecutionStatus.ENTRY_PARTIALLY_FILLED
    assert partial_receipt.stop_order is None
    full = item._order_engine.apply(OrderCommand(OrderCommandType.FILL, receipt.entry_order.order_id, TS + timedelta(seconds=22), fill_quantity=50, fill_price=100.0))
    protected = item.on_order_update(full, timestamp=full.updated_at)
    assert protected.status is PaperExecutionStatus.PROTECTIVE_ORDERS_CREATED
    assert protected.stop_order.quantity == 75
    assert protected.target_order.quantity == 75
    assert protected.stop_order.side is OrderSide.SELL
    assert protected.target_order.side is OrderSide.SELL
    assert protected.stop_order.trigger_price == plan.stop_plan.trigger_price
    assert protected.target_order.limit_price == plan.target_plan.limit_price
    assert protected.stop_order.reduce_only is True
    again = item.on_order_update(full, timestamp=full.updated_at)
    assert again.stop_order.order_id == protected.stop_order.order_id
    assert item.snapshot().order_management_request_count == 3
    assert item.snapshot().paper_submission_count == 3


def test_zero_fill_unknown_order_stale_duplicate_and_cancelled_paths_are_safe():
    item = coordinator()
    receipt = item.execute(execution_request())
    order = item._order_engine.get_order(receipt.entry_order.order_id)
    assert item.on_order_update(replace(order, client_order_id="unknown"), timestamp=TS + timedelta(seconds=21)) is None
    assert item.on_order_update(order, timestamp=TS + timedelta(seconds=21)) is receipt
    cancelled = item.cancel(receipt.receipt_id, timestamp=TS + timedelta(seconds=22), reason="user")
    assert cancelled.status is PaperExecutionStatus.CANCELLED
    filled = replace(order, status=OrderStatus.FILLED, filled_quantity=75, remaining_quantity=0, updated_at=TS + timedelta(seconds=23))
    assert item.on_order_update(filled, timestamp=filled.updated_at).status is PaperExecutionStatus.CANCELLED
    with pytest.raises(ValueError, match="Unknown"):
        item.cancel("missing", timestamp=TS + timedelta(seconds=24))
    item._receipts[cancelled.receipt_id] = replace(cancelled, status=PaperExecutionStatus.COMPLETED)
    with pytest.raises(ValueError, match="Completed"):
        item.cancel(cancelled.receipt_id, timestamp=TS + timedelta(seconds=25))


def test_integration_failure_after_order_creation_preserves_order_and_zero_paper_submissions():
    class FailingPaper(PaperTradingEngine):
        def submit_managed_order(self, order, *, execution_plan, purpose):
            raise RuntimeError("paper boundary unavailable")

    item = coordinator(paper=FailingPaper(EventBus(), instrument="NIFTY", timeframe="1m", safety_mode=RuntimeConfiguration().safety_mode))
    receipt = item.execute(execution_request())
    assert receipt.primary_reason is PaperExecutionReasonCode.PAPER_SUBMISSION_FAILED
    assert item.snapshot().paper_submission_count == 0
    assert item._order_engine.order_count == 1
    recovered = coordinator().execute(execution_request(approved_plan(decision_id="after-failure", client_request_id="after-failure", signal_id="after-failure"), request_id="after-failure"))
    assert recovered.decision is PaperExecutionDecision.APPROVED


def test_application_orchestrator_explicit_command_exposes_snapshot_without_autonomous_execution():
    app = ApplicationOrchestrator(EventBus(), RuntimeConfiguration())
    app.start()
    runtime = app.get_runtime(RuntimeInstrument.NIFTY)
    plan = approved_plan()
    snapshot_before = app.snapshot().runtime_snapshots[0]
    assert snapshot_before.paper_execution.last_receipt is None
    receipt = app.execute_paper_plan(RuntimeInstrument.NIFTY, execution_request(plan))
    assert receipt.decision is PaperExecutionDecision.APPROVED
    snapshot_after = app.snapshot().runtime_snapshots[0]
    assert snapshot_after.paper_execution.last_receipt == receipt
    assert runtime.paper_execution_coordinator.snapshot().broker_order_calls == 0


def test_events_are_published_in_deterministic_order_and_no_second_event_bus_is_created():
    bus = EventBus()
    seen = []
    for name in (
        events.PAPER_EXECUTION_ACCEPTED,
        events.PAPER_ENTRY_ORDER_CREATED,
        events.PAPER_ENTRY_SUBMITTED,
        events.PAPER_EXECUTION_EVALUATED,
    ):
        bus.subscribe(name, lambda payload, event_name=name: seen.append(event_name))
    coordinator(bus=bus).execute(execution_request())
    assert seen == [
        events.PAPER_EXECUTION_ACCEPTED,
        events.PAPER_ENTRY_ORDER_CREATED,
        events.PAPER_ENTRY_SUBMITTED,
        events.PAPER_EXECUTION_EVALUATED,
    ]


def test_safety_searches_for_coordinator_package_have_no_broker_threads_async_sleep_or_eventbus():
    from pathlib import Path

    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("engines/paper_execution_coordinator").glob("*.py"))
    for forbidden in (
        "place_order",
        "modify_order",
        "cancel_order",
        "broker_adapter",
        "kite",
        "zerodha",
        "threading",
        "asyncio",
        "time.sleep",
        "EventBus(",
        "clear_persistent_data=True",
    ):
        assert forbidden not in text
