from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from core.event_bus import EventBus
from core import events
from engines.ai_confidence_calibration import (
    CalibrationDecision,
    ConfidenceBand,
    ConfidenceCalibrationResult,
)
from engines.risk.enums import RiskDecision, RiskReductionReason, RiskRejectionReason, RiskTier
from engines.risk.models import RiskDecisionState
from engines.order_management.enums import OrderSide, OrderType
from engines.strategy.enums import (
    BlockReason,
    EntryReference,
    SetupQuality,
    StopReference,
    StrategyDecision,
    TargetReference,
    TradeDirection,
)
from engines.strategy.models import StrategyDecisionState
from engines.trade_decision_authorization import (
    TradeAuthorizationDecision,
    TradeAuthorizationLifecycle,
    TradeAuthorizationReason,
    TradeAuthorizationRequest,
    TradeAuthorizationResult,
    TradeAuthorizationSnapshot,
    TradeDecisionAuthorizationEngine,
)
from engines.trade_execution_policy.enums import (
    ExecutionDecisionStatus,
    ExecutionMode,
    ExecutionPlanStatus,
    ExecutionReasonCode,
    ExecutionRoutingTarget,
)
from engines.trade_execution_policy.models import TradeExecutionPlan


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 7, 21, 10, 0, tzinfo=IST)


def strategy(**overrides):
    values = {
        "symbol": "NIFTY",
        "timeframe": "1m",
        "timestamp": NOW,
        "decision": StrategyDecision.TRADE_ELIGIBLE,
        "direction": TradeDirection.BULLISH,
        "setup_quality": SetupQuality.HIGH,
        "entry_reference": EntryReference.PRICE_ACTION_RETEST,
        "stop_reference": StopReference.LATEST_SWING,
        "target_reference": TargetReference.NEXT_STRUCTURE,
        "block_reason": BlockReason.NONE,
        "market_bias": "bullish",
        "market_phase": "trending_up",
        "confidence": "high",
        "trading_suitability": "suitable",
        "rationale": ("strategy already decided",),
    }
    values.update(overrides)
    return StrategyDecisionState(**values)


def confidence(**overrides):
    values = {
        "calibration_id": "confidence-1",
        "timestamp": NOW,
        "instrument": RuntimeInstrument.NIFTY,
        "direction": TradeDirection.BULLISH,
        "raw_score": 90.0,
        "penalty_score": 0.0,
        "final_score": 90.0,
        "confidence_band": ConfidenceBand.HIGH,
        "calibration_decision": CalibrationDecision.TRUST,
        "primary_reason": "confidence_trust",
        "evidence": (),
        "supporting_categories": (),
        "conflicting_categories": (),
        "missing_categories": (),
        "stale_categories": (),
        "invalid_categories": (),
        "blocked_reasons": (),
    }
    values.update(overrides)
    return ConfidenceCalibrationResult(**values)


def risk(**overrides):
    values = {
        "symbol": "NIFTY",
        "timeframe": "1m",
        "timestamp": NOW,
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
        "rationale": ("risk already decided",),
        "plan_id": "risk-1",
        "trade_plan_ready": True,
    }
    values.update(overrides)
    return RiskDecisionState(**values)


def policy(**overrides):
    values = {
        "execution_plan_id": "policy-1",
        "created_at": NOW,
        "valid_from": NOW,
        "valid_until": NOW + timedelta(minutes=5),
        "instrument": "NIFTY",
        "direction": TradeDirection.BULLISH,
        "entry_side": OrderSide.BUY,
        "execution_mode": ExecutionMode.PLAN_ONLY,
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
        "routing_target": ExecutionRoutingTarget.PLAN_ONLY,
        "status": ExecutionPlanStatus.PREPARED,
        "decision_status": ExecutionDecisionStatus.APPROVED,
        "primary_reason": ExecutionReasonCode.APPROVED,
        "findings": (),
        "policy_fingerprint": "policy-fp",
        "request_fingerprint": "request-fp",
        "input_fingerprint": "input-fp",
    }
    values.update(overrides)
    return TradeExecutionPlan(**values)


def request(**overrides):
    values = {
        "authorization_id": "auth-1",
        "timestamp": NOW + timedelta(seconds=30),
        "instrument": RuntimeInstrument.NIFTY,
        "strategy_decision": strategy(),
        "confidence_result": confidence(),
        "risk_result": risk(),
        "execution_policy_result": policy(),
        "correlation_id": "corr-1",
    }
    values.update(overrides)
    return TradeAuthorizationRequest(**values)


def started_engine(bus=None):
    engine = TradeDecisionAuthorizationEngine(bus or EventBus(), instrument="NIFTY", timeframe="1m")
    engine.start()
    return engine


def test_models_are_immutable_validate_clock_instrument_multiplier_reasons_and_future_inputs():
    req = request()
    result = started_engine().authorize(req)
    snapshot = started_engine().snapshot()

    with pytest.raises(FrozenInstanceError):
        req.authorization_id = "changed"
    with pytest.raises(FrozenInstanceError):
        result.decision = TradeAuthorizationDecision.BLOCK
    with pytest.raises(FrozenInstanceError):
        snapshot.authorization_count = 99
    with pytest.raises(ValueError, match="timezone-aware"):
        request(timestamp=datetime(2026, 7, 21, 10, 0))
    with pytest.raises(ValueError, match="unsupported instrument"):
        request(instrument="FINNIFTY")
    with pytest.raises(ValueError, match="authorization_multiplier"):
        replace(result, authorization_multiplier=0.75)
    with pytest.raises(FrozenInstanceError):
        result.reasons += (TradeAuthorizationReason.RISK_BLOCKED,)
    with pytest.raises(ValueError, match="strategy_decision timestamp cannot be in the future"):
        request(strategy_decision=strategy(timestamp=NOW + timedelta(minutes=1)))


def test_lifecycle_start_authorize_stop_reset_and_expected_blocks_do_not_fail():
    engine = TradeDecisionAuthorizationEngine(EventBus(), instrument="NIFTY", timeframe="1m")

    assert engine.snapshot().lifecycle_state is TradeAuthorizationLifecycle.CREATED
    with pytest.raises(RuntimeError, match="must be started"):
        engine.authorize(request())
    assert engine.start().lifecycle_state is TradeAuthorizationLifecycle.READY
    first = engine.authorize(request())
    assert first.decision is TradeAuthorizationDecision.AUTHORIZE
    assert engine.snapshot().lifecycle_state is TradeAuthorizationLifecycle.ACTIVE
    engine.authorize(request(authorization_id="auth-2"))
    assert engine.snapshot().lifecycle_state is TradeAuthorizationLifecycle.ACTIVE
    assert engine.stop().lifecycle_state is TradeAuthorizationLifecycle.STOPPED
    with pytest.raises(RuntimeError, match="stopped"):
        engine.authorize(request(authorization_id="stopped"))
    assert engine.reset().lifecycle_state is TradeAuthorizationLifecycle.READY

    blocked = engine.authorize(request(authorization_id="blocked", risk_result=risk(decision=RiskDecision.REJECTED, risk_tier=RiskTier.BLOCKED)))
    invalid = engine.authorize(request(authorization_id="invalid", strategy_decision=object()))
    assert blocked.decision is TradeAuthorizationDecision.BLOCK
    assert invalid.decision is TradeAuthorizationDecision.BLOCK
    assert engine.snapshot().lifecycle_state is TradeAuthorizationLifecycle.ACTIVE

    engine._lifecycle_state = TradeAuthorizationLifecycle.FAILED
    with pytest.raises(RuntimeError, match="failed"):
        engine.authorize(request(authorization_id="failed"))
    assert engine.reset().lifecycle_state is TradeAuthorizationLifecycle.READY


def test_authorization_reduce_block_priority_reasons_and_multipliers():
    authorize = started_engine().authorize(request())
    confidence_reduced = started_engine().authorize(
        request(confidence_result=confidence(calibration_decision=CalibrationDecision.REDUCE, final_score=40.0, confidence_band=ConfidenceBand.LOW))
    )
    risk_reduced = started_engine().authorize(
        request(risk_result=risk(risk_tier=RiskTier.REDUCED, reduction_reason=RiskReductionReason.RECENT_LOSSES))
    )
    policy_reduced = started_engine().authorize(
        request(execution_policy_result=policy(status=ExecutionPlanStatus.AWAITING_MANUAL_APPROVAL, decision_status=ExecutionDecisionStatus.APPROVED))
    )
    confidence_blocked = started_engine().authorize(
        request(confidence_result=confidence(calibration_decision=CalibrationDecision.BLOCK, confidence_band=ConfidenceBand.BLOCKED))
    )
    risk_blocked = started_engine().authorize(request(risk_result=risk(decision=RiskDecision.REJECTED, risk_tier=RiskTier.BLOCKED)))
    policy_blocked = started_engine().authorize(
        request(execution_policy_result=policy(status=ExecutionPlanStatus.REJECTED, decision_status=ExecutionDecisionStatus.REJECTED))
    )

    assert authorize.decision is TradeAuthorizationDecision.AUTHORIZE
    assert authorize.authorization_multiplier == 1.0
    assert confidence_reduced.decision is risk_reduced.decision is policy_reduced.decision is TradeAuthorizationDecision.REDUCE
    assert confidence_reduced.authorization_multiplier == 0.5
    assert risk_reduced.authorization_multiplier == 0.5
    assert policy_reduced.authorization_multiplier == 0.5
    assert confidence_blocked.decision is risk_blocked.decision is policy_blocked.decision is TradeAuthorizationDecision.BLOCK
    assert confidence_blocked.authorization_multiplier == 0.0
    assert risk_blocked.authorization_multiplier == 0.0
    assert policy_blocked.authorization_multiplier == 0.0

    mixed = started_engine().authorize(
        request(
            confidence_result=confidence(calibration_decision=CalibrationDecision.REDUCE, final_score=40.0, confidence_band=ConfidenceBand.LOW),
            risk_result=risk(decision=RiskDecision.REJECTED, risk_tier=RiskTier.BLOCKED),
            execution_policy_result=policy(status=ExecutionPlanStatus.AWAITING_MANUAL_APPROVAL, decision_status=ExecutionDecisionStatus.LOCKED),
        )
    )
    assert mixed.decision is TradeAuthorizationDecision.BLOCK
    assert mixed.primary_reason is TradeAuthorizationReason.RISK_BLOCKED
    assert mixed.reasons == (
        TradeAuthorizationReason.RISK_BLOCKED,
        TradeAuthorizationReason.POLICY_BLOCKED,
        TradeAuthorizationReason.CONFIDENCE_REDUCED,
    )


@pytest.mark.parametrize(
    "blocking_decision",
    (
        ExecutionDecisionStatus.REJECTED,
        ExecutionDecisionStatus.LOCKED,
        ExecutionDecisionStatus.INVALID,
        ExecutionDecisionStatus.EXPIRED,
    ),
)
def test_policy_blocking_decision_overrides_manual_approval_reduction(blocking_decision):
    engine = started_engine()

    blocked = engine.authorize(
        request(
            authorization_id=f"policy-block-{blocking_decision.value}",
            execution_policy_result=policy(
                status=ExecutionPlanStatus.AWAITING_MANUAL_APPROVAL,
                decision_status=blocking_decision,
            ),
        )
    )
    ordinary_manual_approval = started_engine().authorize(
        request(
            execution_policy_result=policy(
                status=ExecutionPlanStatus.AWAITING_MANUAL_APPROVAL,
                decision_status=ExecutionDecisionStatus.APPROVED,
            )
        )
    )
    blocking_plan = started_engine().authorize(
        request(
            execution_policy_result=policy(
                status=ExecutionPlanStatus.LOCKED,
                decision_status=ExecutionDecisionStatus.APPROVED,
            )
        )
    )

    assert blocked.decision is TradeAuthorizationDecision.BLOCK
    assert blocked.authorization_multiplier == 0.0
    assert blocked.primary_reason is TradeAuthorizationReason.POLICY_BLOCKED
    assert blocked.reasons == (TradeAuthorizationReason.POLICY_BLOCKED,)
    assert ordinary_manual_approval.decision is TradeAuthorizationDecision.REDUCE
    assert ordinary_manual_approval.primary_reason is TradeAuthorizationReason.POLICY_REDUCED
    assert blocking_plan.primary_reason is TradeAuthorizationReason.POLICY_BLOCKED
    assert engine.snapshot().lifecycle_state is TradeAuthorizationLifecycle.ACTIVE


def test_policy_block_overrides_reductions_preserves_lower_reasons_and_is_idempotent():
    bus = EventBus()
    completed = []
    bus.subscribe(events.TRADE_AUTHORIZATION_COMPLETED, completed.append)
    engine = started_engine(bus)
    blocked_request = request(
        authorization_id="policy-block-over-reductions",
        confidence_result=confidence(calibration_decision=CalibrationDecision.REDUCE, final_score=40.0, confidence_band=ConfidenceBand.LOW),
        risk_result=risk(risk_tier=RiskTier.REDUCED, reduction_reason=RiskReductionReason.RECENT_LOSSES),
        execution_policy_result=policy(status=ExecutionPlanStatus.AWAITING_MANUAL_APPROVAL, decision_status=ExecutionDecisionStatus.REJECTED),
    )

    first = engine.authorize(blocked_request)
    second = engine.authorize(blocked_request)
    snapshot = engine.snapshot()

    assert first is second
    assert first.decision is TradeAuthorizationDecision.BLOCK
    assert first.authorization_multiplier == 0.0
    assert first.primary_reason is TradeAuthorizationReason.POLICY_BLOCKED
    assert first.reasons == (
        TradeAuthorizationReason.POLICY_BLOCKED,
        TradeAuthorizationReason.CONFIDENCE_REDUCED,
        TradeAuthorizationReason.RISK_REDUCED,
    )
    assert first.direction is TradeDirection.BULLISH
    assert snapshot.authorization_count == 1
    assert snapshot.blocked_count == 1
    assert snapshot.lifecycle_state is TradeAuthorizationLifecycle.ACTIVE
    assert snapshot.broker_order_calls == 0
    assert snapshot.mutation_calls == 0
    assert snapshot.live_order_submission_enabled is False
    assert len(completed) == 1


def test_consistency_direction_mismatch_and_orchestrator_cross_instrument_rejection():
    instrument_mismatch = started_engine().authorize(request(risk_result=risk(symbol="BANKNIFTY")))
    confidence_direction = started_engine().authorize(request(confidence_result=confidence(direction=TradeDirection.BEARISH)))
    risk_direction = started_engine().authorize(request(risk_result=risk(direction=TradeDirection.BEARISH)))
    policy_direction = started_engine().authorize(request(execution_policy_result=policy(direction=TradeDirection.BEARISH)))

    assert instrument_mismatch.primary_reason is TradeAuthorizationReason.INSTRUMENT_MISMATCH
    assert confidence_direction.primary_reason is TradeAuthorizationReason.DIRECTION_MISMATCH
    assert risk_direction.primary_reason is TradeAuthorizationReason.DIRECTION_MISMATCH
    assert policy_direction.primary_reason is TradeAuthorizationReason.DIRECTION_MISMATCH
    assert confidence_direction.direction is TradeDirection.BULLISH

    app = ApplicationOrchestrator(EventBus(), RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY)))
    app.start()
    with pytest.raises(ValueError, match="does not match runtime"):
        app.authorize_trade_decision(RuntimeInstrument.BANKNIFTY, request())


def test_freshness_uses_request_timestamp_lists_stale_inputs_and_has_no_wall_clock_dependency():
    stale_time = NOW - timedelta(seconds=301)
    result = started_engine().authorize(
        request(
            timestamp=NOW,
            strategy_decision=strategy(timestamp=stale_time),
            confidence_result=confidence(timestamp=stale_time),
            risk_result=risk(timestamp=stale_time),
            execution_policy_result=policy(created_at=stale_time, valid_from=stale_time, valid_until=NOW + timedelta(minutes=1)),
        )
    )

    assert result.decision is TradeAuthorizationDecision.BLOCK
    assert result.primary_reason is TradeAuthorizationReason.STALE_INPUT
    assert result.stale_inputs == (
        "strategy_decision",
        "confidence_result",
        "risk_result",
        "execution_policy_result",
    )

    fresh_again = started_engine().authorize(request(timestamp=NOW + timedelta(seconds=300)))
    assert fresh_again.decision is TradeAuthorizationDecision.AUTHORIZE


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("strategy_decision", object()),
        ("confidence_result", object()),
        ("risk_result", object()),
        ("execution_policy_result", object()),
    ),
)
def test_invalid_inputs_block_normally_are_listed_stored_and_do_not_fail(field, value):
    engine = started_engine()
    result = engine.authorize(request(authorization_id=f"invalid-{field}", **{field: value}))

    assert result.decision is TradeAuthorizationDecision.BLOCK
    assert result.primary_reason is TradeAuthorizationReason.INVALID_INPUT
    assert result.invalid_inputs == (field,)
    assert engine.get_result(result.authorization_id) is result
    assert engine.snapshot().lifecycle_state is TradeAuthorizationLifecycle.ACTIVE


def test_idempotency_duplicate_events_and_changed_duplicate_preserve_state():
    bus = EventBus()
    completed = []
    bus.subscribe(events.TRADE_AUTHORIZATION_COMPLETED, completed.append)
    engine = started_engine(bus)
    req = request(authorization_id="dupe")

    first = engine.authorize(req)
    second = engine.authorize(req)
    snapshot = engine.snapshot()

    assert second is first
    assert snapshot.authorization_count == 1
    assert len(completed) == 1
    with pytest.raises(ValueError, match="authorization_id already exists"):
        engine.authorize(request(authorization_id="dupe", confidence_result=confidence(calibration_decision=CalibrationDecision.REDUCE, final_score=40.0, confidence_band=ConfidenceBand.LOW)))
    assert engine.snapshot() == snapshot


def test_symbol_runtime_orchestrator_snapshot_reset_and_no_upstream_invocation():
    app = ApplicationOrchestrator(EventBus(), RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY)))
    app.start()
    runtime = app.get_runtime(RuntimeInstrument.NIFTY)

    calls = {"strategy": 0, "confidence": 0, "risk": 0, "policy": 0}
    runtime.run_strategy = lambda *args, **kwargs: calls.__setitem__("strategy", calls["strategy"] + 1)
    runtime.calibrate_ai_confidence = lambda *args, **kwargs: calls.__setitem__("confidence", calls["confidence"] + 1)
    runtime.run_risk = lambda *args, **kwargs: calls.__setitem__("risk", calls["risk"] + 1)
    runtime.evaluate_execution_policy = lambda *args, **kwargs: calls.__setitem__("policy", calls["policy"] + 1)

    result = app.authorize_trade_decision(RuntimeInstrument.NIFTY, request())
    snapshot = app.snapshot().runtime_snapshots[0]

    assert result.decision is TradeAuthorizationDecision.AUTHORIZE
    assert runtime.trade_authorization_engine is not app.get_runtime(RuntimeInstrument.BANKNIFTY).trade_authorization_engine
    assert snapshot.trade_authorization is not None
    assert snapshot.trade_authorization.last_result is result
    assert calls == {"strategy": 0, "confidence": 0, "risk": 0, "policy": 0}
    app.reset_trade_authorization(RuntimeInstrument.NIFTY)
    assert app.get_trade_authorization_snapshot(RuntimeInstrument.NIFTY).authorization_count == 0
    assert app.get_confidence_snapshot(RuntimeInstrument.NIFTY).calibration_count == 0


def test_events_and_snapshot_safety_constants_remain_zero_and_false():
    bus = EventBus()
    seen = {name: [] for name in (
        events.TRADE_AUTHORIZATION_COMPLETED,
        events.TRADE_AUTHORIZATION_APPROVED,
        events.TRADE_AUTHORIZATION_REDUCED,
        events.TRADE_AUTHORIZATION_BLOCKED,
        events.TRADE_AUTHORIZATION_STATE_UPDATED,
    )}
    for name in seen:
        bus.subscribe(name, lambda payload, event_name=name: seen[event_name].append(payload))
    engine = started_engine(bus)

    engine.authorize(request(authorization_id="approved"))
    engine.authorize(
        request(
            authorization_id="reduced",
            confidence_result=confidence(calibration_decision=CalibrationDecision.REDUCE, final_score=40.0, confidence_band=ConfidenceBand.LOW),
        )
    )
    engine.authorize(request(authorization_id="blocked", risk_result=risk(decision=RiskDecision.REJECTED, risk_tier=RiskTier.BLOCKED)))
    snapshot = engine.snapshot()

    assert len(seen[events.TRADE_AUTHORIZATION_COMPLETED]) == 3
    assert len(seen[events.TRADE_AUTHORIZATION_APPROVED]) == 1
    assert len(seen[events.TRADE_AUTHORIZATION_REDUCED]) == 1
    assert len(seen[events.TRADE_AUTHORIZATION_BLOCKED]) == 1
    assert snapshot.broker_order_calls == 0
    assert snapshot.mutation_calls == 0
    assert snapshot.live_order_submission_enabled is False


def test_authorization_package_has_no_execution_recalculation_network_threads_timers_or_eventbus_creation():
    source = "\n".join(path.read_text(encoding="utf-8") for path in Path("engines/trade_decision_authorization").glob("*.py"))
    for forbidden in (
        "place_order",
        "modify_order",
        "cancel_order",
        "execute_paper",
        "reconcile",
        "apply_position",
        "run_strategy",
        "calibrate(",
        "evaluate_risk",
        "evaluate_policy",
        "requests",
        "httpx",
        "threading",
        "asyncio",
        "time.sleep",
        "QTimer",
        "EventBus(",
    ):
        assert forbidden not in source
