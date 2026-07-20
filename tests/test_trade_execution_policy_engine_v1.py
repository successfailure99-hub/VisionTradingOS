from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from core.event_bus import EventBus
from core import events
from engines.order_management.enums import OrderSide, OrderType
from engines.risk.enums import (
    RiskDecision,
    RiskDecisionStatus,
    RiskReasonCode,
    RiskRejectionReason,
    RiskReductionReason,
    RiskTier,
)
from engines.risk.models import RiskDecisionRecord, RiskDecisionState
from engines.strategy.enums import TradeDirection
from engines.trade_execution_policy import (
    ExecutionDecisionStatus,
    ExecutionLifecycleState,
    ExecutionMode,
    ExecutionPlanStatus,
    ExecutionPolicy,
    ExecutionReasonCode,
    ExecutionRequest,
    InstrumentTickSize,
    TradeExecutionPolicyEngine,
)


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


def legacy_risk(**overrides):
    values = {
        "symbol": "NIFTY",
        "timeframe": "1m",
        "timestamp": TS,
        "decision": RiskDecision.APPROVED,
        "risk_tier": RiskTier.STANDARD,
        "rejection_reason": RiskRejectionReason.NONE,
        "reduction_reason": RiskReductionReason.NONE,
        "direction": TradeDirection.BULLISH,
        "account_equity": 100000.0,
        "realized_pnl_today": 0.0,
        "daily_loss_limit_amount": 2000.0,
        "remaining_daily_loss_capacity": 2000.0,
        "applied_risk_percent": 1.0,
        "risk_budget": 1000.0,
        "entry_price": 100.0,
        "stop_price": 95.0,
        "target_price": 110.0,
        "stop_distance": 5.0,
        "target_distance": 10.0,
        "reward_risk_ratio": 2.0,
        "lot_size": 75,
        "requested_lots": 1,
        "maximum_permitted_lots": 1,
        "approved_lots": 1,
        "approved_quantity": 75,
        "estimated_risk_amount": 375.0,
        "estimated_reward_amount": 750.0,
        "rationale": ("approved",),
        "plan_id": "legacy-risk-1",
        "trade_plan_ready": True,
    }
    values.update(overrides)
    return RiskDecisionState(**values)


def request(**overrides):
    values = {
        "instrument": "NIFTY",
        "timestamp": TS + timedelta(seconds=10),
        "risk_decision": risk_record(),
        "execution_mode": ExecutionMode.PLAN_ONLY,
        "requested_order_type": OrderType.LIMIT,
        "requested_entry_price": 100.0,
        "market_reference_price": 100.0,
        "requested_quantity": 75,
        "manual_approval": True,
        "signal_id": "signal-1",
        "strategy_id": "strategy-1",
        "client_request_id": "client-1",
    }
    values.update(overrides)
    return ExecutionRequest(**values)


def engine(policy=None, bus=None):
    return TradeExecutionPolicyEngine(bus or EventBus(), instrument="NIFTY", timeframe="1m", policy=policy)


def test_policy_models_are_immutable_validate_inputs_and_canonicalize_mappings():
    source = {"NIFTY": 0.05, "BANKNIFTY": 0.05}
    policy = ExecutionPolicy(price_tick_by_instrument=source)
    source["NIFTY"] = 1.0
    assert policy.tick_size_for("NIFTY") == 0.05
    assert isinstance(policy.price_tick_by_instrument, tuple)
    with pytest.raises(FrozenInstanceError):
        policy.enabled = False
    with pytest.raises(TypeError):
        ExecutionPolicy(enabled="yes")
    with pytest.raises(ValueError):
        ExecutionPolicy(allowed_instruments=("CRUDEOIL",))
    with pytest.raises(ValueError):
        ExecutionPolicy(price_tick_by_instrument={"NIFTY": 0})
    with pytest.raises(ValueError):
        ExecutionRequest(instrument="NIFTY", timestamp=datetime(2026, 7, 20, 9, 30), risk_decision=risk_record())
    with pytest.raises(ValueError):
        ExecutionRequest(instrument="NIFTY", timestamp=TS, risk_decision=risk_record(), requested_quantity=0)


def test_approved_and_reduced_risk_decisions_prepare_deterministic_plan_only_plans():
    item = engine()
    reduced = risk_record(status=RiskDecisionStatus.APPROVED_WITH_REDUCED_SIZE, decision_id="risk-reduced")
    first = item.evaluate(request(risk_decision=reduced, client_request_id="client-reduced", signal_id="signal-reduced"))
    second = item.evaluate(request(risk_decision=reduced, client_request_id="client-reduced", signal_id="signal-reduced"))
    assert first is second
    assert first.decision_status is ExecutionDecisionStatus.APPROVED
    assert first.status is ExecutionPlanStatus.PREPARED
    assert first.routing_target.value == "plan_only"
    assert first.entry_side is OrderSide.BUY
    assert first.entry_quantity == 75
    assert first.broker_submission_allowed is False
    assert first.broker_order_calls == 0


@pytest.mark.parametrize(
    ("risk", "reason"),
    [
        (risk_record(status=RiskDecisionStatus.REJECTED, approved=False, approved_quantity=0, approved_lots=0, primary_reason=RiskReasonCode.INVALID_PLAN), ExecutionReasonCode.RISK_NOT_APPROVED),
        (risk_record(status=RiskDecisionStatus.LOCKED, approved=False, approved_quantity=0, approved_lots=0, primary_reason=RiskReasonCode.MANUAL_LOCK_ACTIVE), ExecutionReasonCode.RISK_NOT_APPROVED),
        (risk_record(status=RiskDecisionStatus.INVALID, approved=False, approved_quantity=0, approved_lots=0, primary_reason=RiskReasonCode.INVALID_PLAN), ExecutionReasonCode.RISK_NOT_APPROVED),
    ],
)
def test_rejected_locked_and_invalid_risk_decisions_are_blocked(risk, reason):
    plan = engine().evaluate(request(risk_decision=risk, requested_quantity=1, client_request_id=f"client-{risk.status.value}"))
    assert plan.decision_status is ExecutionDecisionStatus.REJECTED
    assert plan.primary_reason is reason
    assert plan.status is ExecutionPlanStatus.REJECTED


def test_quantity_gating_exact_reduction_and_increase_rules():
    assert engine().evaluate(request(requested_quantity=75)).decision_status is ExecutionDecisionStatus.APPROVED
    reduced_blocked = engine().evaluate(request(requested_quantity=50, client_request_id="client-reduce"))
    assert reduced_blocked.primary_reason is ExecutionReasonCode.QUANTITY_MISMATCH
    reduced_policy = ExecutionPolicy(quantity_must_match_risk_decision=False, allow_quantity_reduction=True)
    reduced = engine(reduced_policy).evaluate(request(requested_quantity=50, client_request_id="client-reduce-ok"))
    assert reduced.decision_status is ExecutionDecisionStatus.APPROVED
    increased = engine().evaluate(request(requested_quantity=76, client_request_id="client-inc"))
    assert increased.primary_reason is ExecutionReasonCode.QUANTITY_INCREASE_BLOCKED


def test_manual_approval_required_by_default_and_replacement_approval_is_immutable():
    item = engine()
    awaiting = item.evaluate(request(manual_approval=False))
    assert awaiting.decision_status is ExecutionDecisionStatus.LOCKED
    assert awaiting.status is ExecutionPlanStatus.AWAITING_MANUAL_APPROVAL
    assert awaiting.primary_reason is ExecutionReasonCode.MISSING_MANUAL_APPROVAL
    approved = item.approve_manual(awaiting.execution_plan_id, timestamp=TS + timedelta(seconds=20))
    assert approved.execution_plan_id == awaiting.execution_plan_id
    assert approved is not awaiting
    assert approved.status is ExecutionPlanStatus.PREPARED
    assert approved.manual_approval_present is True
    assert awaiting.manual_approval_present is False


def test_manual_approval_cannot_override_rejected_or_expired_plans():
    item = engine()
    blocked = item.evaluate(request(risk_decision=risk_record(status=RiskDecisionStatus.REJECTED, approved=False, approved_quantity=0, approved_lots=0), requested_quantity=1))
    with pytest.raises(ValueError):
        item.approve_manual(blocked.execution_plan_id, timestamp=TS + timedelta(seconds=20))
    awaiting = item.evaluate(request(manual_approval=False, client_request_id="client-expire", signal_id="signal-expire", risk_decision=risk_record(decision_id="risk-expire")))
    expired = item.approve_manual(awaiting.execution_plan_id, timestamp=awaiting.valid_until)
    assert expired.status is ExecutionPlanStatus.EXPIRED
    assert expired.decision_status is ExecutionDecisionStatus.EXPIRED


def test_order_type_policy_limit_market_stop_limit_and_live_mode_blocking():
    assert engine().evaluate(request(requested_order_type=OrderType.LIMIT)).decision_status is ExecutionDecisionStatus.APPROVED
    market = engine().evaluate(request(requested_order_type=OrderType.MARKET, requested_entry_price=None, client_request_id="market"))
    assert market.primary_reason is ExecutionReasonCode.MARKET_ORDER_BLOCKED
    allowed_market = engine(ExecutionPolicy(allow_market_orders=True)).evaluate(
        request(requested_order_type=OrderType.MARKET, requested_entry_price=None, client_request_id="market-ok", signal_id="market-ok", risk_decision=risk_record(decision_id="risk-market"))
    )
    assert allowed_market.decision_status is ExecutionDecisionStatus.APPROVED
    stop_missing = engine().evaluate(request(requested_order_type=OrderType.STOP_LIMIT, client_request_id="stop-missing"))
    assert stop_missing.primary_reason is ExecutionReasonCode.INVALID_TRIGGER_PRICE
    stop_ok = engine().evaluate(request(requested_order_type=OrderType.STOP_LIMIT, trigger_price=99.5, client_request_id="stop-ok", signal_id="stop-ok", risk_decision=risk_record(decision_id="risk-stop")))
    assert stop_ok.decision_status is ExecutionDecisionStatus.APPROVED
    live = engine().evaluate(request(execution_mode="LIVE", client_request_id="live"))
    assert live.primary_reason is ExecutionReasonCode.LIVE_EXECUTION_BLOCKED


def test_tick_alignment_and_slippage_policy_are_deterministic_at_boundaries():
    assert engine().evaluate(request(requested_entry_price=100.15, market_reference_price=100.0)).primary_reason is ExecutionReasonCode.SLIPPAGE_LIMIT_EXCEEDED
    boundary = engine(ExecutionPolicy(maximum_entry_slippage_percentage=0.10)).evaluate(
        request(requested_entry_price=100.1, market_reference_price=100.0, client_request_id="slip-boundary", signal_id="slip-boundary", risk_decision=risk_record(decision_id="risk-slip"))
    )
    assert boundary.decision_status is ExecutionDecisionStatus.APPROVED
    point_policy = ExecutionPolicy(maximum_entry_slippage_points=0.05, maximum_entry_slippage_percentage=None)
    point = engine(point_policy).evaluate(request(requested_entry_price=100.1, market_reference_price=100.0, client_request_id="slip-point"))
    assert point.primary_reason is ExecutionReasonCode.SLIPPAGE_LIMIT_EXCEEDED
    unaligned = engine().evaluate(request(requested_entry_price=100.03, market_reference_price=100.0, client_request_id="unaligned"))
    assert unaligned.primary_reason is ExecutionReasonCode.PRICE_NOT_TICK_ALIGNED


def test_bullish_and_bearish_protective_plans_use_opposite_side_and_reduce_only():
    bullish = engine().evaluate(request())
    assert bullish.stop_plan.side is OrderSide.SELL
    assert bullish.target_plan.side is OrderSide.SELL
    assert bullish.stop_plan.reduce_only is True
    assert bullish.target_plan.quantity == bullish.entry_quantity
    bearish_risk = risk_record(
        decision_id="risk-bear",
        direction=TradeDirection.BEARISH,
        entry_price=100.0,
        stop_loss_price=105.0,
        target_price=90.0,
    )
    bearish = engine().evaluate(request(risk_decision=bearish_risk, client_request_id="bear", signal_id="bear"))
    assert bearish.entry_side is OrderSide.SELL
    assert bearish.stop_plan.side is OrderSide.BUY
    assert bearish.target_plan.side is OrderSide.BUY


def test_missing_and_invalid_protective_geometry_is_blocked():
    no_stop = engine().evaluate(request(risk_decision=risk_record(stop_loss_price=None), client_request_id="no-stop"))
    assert no_stop.primary_reason is ExecutionReasonCode.MISSING_STOP_PLAN
    no_target = engine().evaluate(request(risk_decision=risk_record(decision_id="no-target", target_price=None), client_request_id="no-target"))
    assert no_target.primary_reason is ExecutionReasonCode.MISSING_TARGET_PLAN
    bad_stop = engine().evaluate(request(risk_decision=risk_record(decision_id="bad-stop", stop_loss_price=101.0), client_request_id="bad-stop"))
    assert bad_stop.primary_reason is ExecutionReasonCode.INVALID_STOP_GEOMETRY
    bad_target = engine().evaluate(request(risk_decision=risk_record(decision_id="bad-target", target_price=99.0), client_request_id="bad-target"))
    assert bad_target.primary_reason is ExecutionReasonCode.INVALID_TARGET_GEOMETRY


def test_decision_staleness_plan_validity_and_replay_fingerprint_stability():
    fresh = engine().evaluate(request(timestamp=TS + timedelta(seconds=60)))
    assert fresh.decision_status is ExecutionDecisionStatus.APPROVED
    stale = engine().evaluate(request(timestamp=TS + timedelta(seconds=61), client_request_id="stale"))
    assert stale.primary_reason is ExecutionReasonCode.RISK_DECISION_EXPIRED
    assert stale.decision_status is ExecutionDecisionStatus.EXPIRED
    capped = engine().evaluate(request(valid_until=TS + timedelta(seconds=1000), client_request_id="cap", signal_id="cap", risk_decision=risk_record(decision_id="risk-cap")))
    assert capped.valid_until == capped.created_at + timedelta(seconds=120)
    one = engine().evaluate(request(client_request_id="det", signal_id="det", risk_decision=risk_record(decision_id="risk-det")))
    two = engine().evaluate(request(client_request_id="det", signal_id="det", risk_decision=risk_record(decision_id="risk-det")))
    assert one.execution_plan_id == two.execution_plan_id
    assert one.input_fingerprint == two.input_fingerprint


def test_duplicate_prevention_by_client_risk_and_signal_and_cancel_allows_explicit_behavior():
    item = engine()
    first = item.evaluate(request())
    same_client = item.evaluate(request(risk_decision=risk_record(decision_id="risk-2"), signal_id="signal-2"))
    assert same_client.primary_reason is ExecutionReasonCode.DUPLICATE_EXECUTION_PLAN
    same_risk = item.evaluate(request(client_request_id="client-3", signal_id="signal-3"))
    assert same_risk.primary_reason is ExecutionReasonCode.RISK_DECISION_ALREADY_HAS_PLAN
    same_signal = item.evaluate(request(risk_decision=risk_record(decision_id="risk-4"), client_request_id="client-4"))
    assert same_signal.primary_reason is ExecutionReasonCode.SIGNAL_ALREADY_HAS_PLAN
    cancelled = item.cancel_plan(first.execution_plan_id, timestamp=TS + timedelta(seconds=20))
    assert cancelled.status is ExecutionPlanStatus.CANCELLED
    recreated = item.evaluate(request(client_request_id="client-5", signal_id="signal-5", risk_decision=risk_record(decision_id="risk-5")))
    assert recreated.decision_status is ExecutionDecisionStatus.APPROVED


def test_lifecycle_snapshot_counts_and_policy_rejection_does_not_fail_engine():
    item = engine(ExecutionPolicy(enabled=False))
    assert item.snapshot().lifecycle_state is ExecutionLifecycleState.CREATED
    item.start()
    assert item.snapshot().lifecycle_state is ExecutionLifecycleState.READY
    rejected = item.evaluate(request())
    assert rejected.primary_reason is ExecutionReasonCode.POLICY_DISABLED
    assert item.snapshot().lifecycle_state is ExecutionLifecycleState.READY
    item.stop()
    stopped = item.evaluate(request(client_request_id="stopped"))
    assert stopped.primary_reason is ExecutionReasonCode.ENGINE_STOPPED
    snap = item.snapshot()
    assert snap.broker_order_calls == 0
    assert isinstance(snap.active_plan_ids, tuple)


def test_events_publish_once_for_prepared_locked_rejected_approved_cancelled_and_expired():
    bus = EventBus()
    seen = {name: [] for name in (
        events.EXECUTION_POLICY_EVALUATED,
        events.EXECUTION_PLAN_PREPARED,
        events.EXECUTION_PLAN_LOCKED,
        events.EXECUTION_PLAN_REJECTED,
        events.EXECUTION_PLAN_APPROVED,
        events.EXECUTION_PLAN_CANCELLED,
        events.EXECUTION_PLAN_EXPIRED,
    )}
    for name in seen:
        bus.subscribe(name, lambda payload, event_name=name: seen[event_name].append(payload))
    item = engine(bus=bus)
    prepared = item.evaluate(request())
    item.evaluate(request())
    awaiting = item.evaluate(request(manual_approval=False, client_request_id="await", signal_id="await", risk_decision=risk_record(decision_id="risk-await")))
    item.approve_manual(awaiting.execution_plan_id, timestamp=TS + timedelta(seconds=20))
    rejected = item.evaluate(request(risk_decision=risk_record(decision_id="risk-rej", status=RiskDecisionStatus.REJECTED, approved=False, approved_quantity=0, approved_lots=0), requested_quantity=1, client_request_id="rej", signal_id="rej"))
    item.cancel_plan(prepared.execution_plan_id, timestamp=TS + timedelta(seconds=30))
    item.expire_plan(awaiting.execution_plan_id, timestamp=TS + timedelta(seconds=40))
    assert len(seen[events.EXECUTION_PLAN_PREPARED]) == 1
    assert len(seen[events.EXECUTION_PLAN_LOCKED]) == 1
    assert len(seen[events.EXECUTION_PLAN_APPROVED]) == 1
    assert len(seen[events.EXECUTION_PLAN_REJECTED]) == 1
    assert len(seen[events.EXECUTION_PLAN_CANCELLED]) == 1
    assert len(seen[events.EXECUTION_PLAN_EXPIRED]) == 1
    assert rejected.primary_reason is ExecutionReasonCode.RISK_NOT_APPROVED


def test_application_runtime_owns_engine_and_plan_only_never_creates_order_or_paper_order():
    app = ApplicationOrchestrator(EventBus(), RuntimeConfiguration())
    app.start()
    runtime = app.get_runtime(RuntimeInstrument.NIFTY)
    risk = legacy_risk()
    runtime.risk_engine.record_decision(risk)
    plan = app.evaluate_execution_policy(
        RuntimeInstrument.NIFTY,
        ExecutionRequest(
            instrument="NIFTY",
            timestamp=TS + timedelta(seconds=10),
            risk_decision=risk,
            requested_order_type=OrderType.LIMIT,
            requested_entry_price=100.0,
            market_reference_price=100.0,
            requested_quantity=75,
            manual_approval=True,
            signal_id="app-signal",
            strategy_id="app-strategy",
            client_request_id="app-client",
        ),
    )
    assert plan.execution_mode is ExecutionMode.PLAN_ONLY
    assert app.create_order_from_execution_plan(RuntimeInstrument.NIFTY, plan) is None
    snapshot = app.snapshot().runtime_snapshots[0]
    assert snapshot.execution_policy.last_plan == plan
    assert snapshot.latest_order is None
    assert snapshot.paper_trading.diagnostics.orders_created == 0
    assert snapshot.paper_trading.diagnostics.broker_order_calls == 0


def test_application_paper_mode_uses_order_management_boundary_only_after_approval():
    app = ApplicationOrchestrator(EventBus(), RuntimeConfiguration())
    app.start()
    runtime = app.get_runtime("NIFTY")
    risk = legacy_risk(plan_id="legacy-risk-paper")
    runtime.risk_engine.record_decision(risk)
    awaiting = app.evaluate_execution_policy(
        "NIFTY",
        ExecutionRequest(
            instrument="NIFTY",
            timestamp=TS,
            risk_decision=risk,
            execution_mode=ExecutionMode.PAPER,
            requested_order_type=OrderType.LIMIT,
            requested_entry_price=100.0,
            market_reference_price=100.0,
            requested_quantity=75,
            manual_approval=False,
            signal_id="paper-signal",
            strategy_id="paper-strategy",
            client_request_id="paper-client",
        ),
    )
    assert app.create_order_from_execution_plan("NIFTY", awaiting) is None
    approved = runtime.execution_policy_engine.approve_manual(awaiting.execution_plan_id, timestamp=TS + timedelta(seconds=1))
    order = app.create_order_from_execution_plan("NIFTY", approved)
    assert order is not None
    assert order.quantity == 75
    assert runtime.paper_trading_engine.snapshot().diagnostics.orders_created == 0
    assert runtime.order_engine.order_count == 1
    assert runtime.execution_policy_engine.snapshot().broker_order_calls == 0


def test_safety_searches_for_new_package_have_no_broker_threads_async_sleep_or_credentials():
    from pathlib import Path

    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("engines/trade_execution_policy").glob("*.py"))
    for forbidden in (
        "place_order",
        "modify_order",
        "cancel_order",
        "broker_adapter.place",
        "kite.place_order",
        "threading",
        "asyncio",
        "time.sleep",
        "EventBus(",
        "api_key",
        "api_secret",
        "access_token",
        "request_token",
        "READY_FOR_BROKER",
    ):
        assert forbidden not in text
