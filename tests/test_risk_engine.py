"""
Tests for Risk Engine V1.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from core.event_bus import EventBus
from core.events import RISK_UPDATED
from engines.ai_reasoning.enums import ReasoningConfidence, TradingSuitability
from engines.market_context.enums import MarketBias, MarketPhase
from engines.risk import (
    AccountRiskState,
    RiskCalculator,
    RiskDecision,
    RiskDecisionState,
    RiskEngine,
    RiskPolicy,
    RiskRejectionReason,
    RiskReductionReason,
    RiskSnapshot,
    RiskTier,
    TradeRiskPlan,
)
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


TS = datetime(2026, 7, 10, 10, 0)


def assert_raises(expected_error, callback):
    try:
        callback()
    except expected_error:
        return
    raise AssertionError(f"Expected {expected_error}")


def policy(**overrides):
    values = {
        "max_risk_percent": 2.0,
        "reduced_risk_percent": 1.0,
        "max_daily_loss_percent": 5.0,
        "max_consecutive_losses": 3,
        "reduced_after_consecutive_losses": 2,
        "max_trades_per_day": 5,
        "reduced_after_trades": 3,
        "max_lots": 5,
        "minimum_reward_risk": 1.5,
    }
    values.update(overrides)
    return RiskPolicy(**values)


def account(**overrides):
    values = {
        "account_equity": 100000.0,
        "realized_pnl_today": 0.0,
        "trades_today": 0,
        "consecutive_losses": 0,
    }
    values.update(overrides)
    return AccountRiskState(**values)


def trade_plan(**overrides):
    values = {
        "entry_price": 100.0,
        "stop_price": 90.0,
        "target_price": 120.0,
        "lot_size": 75,
        "requested_lots": 2,
    }
    values.update(overrides)
    return TradeRiskPlan(**values)


def strategy(**overrides):
    values = {
        "symbol": "NIFTY",
        "timeframe": "1m",
        "timestamp": TS,
        "decision": StrategyDecision.TRADE_ELIGIBLE,
        "direction": TradeDirection.BULLISH,
        "setup_quality": SetupQuality.HIGH,
        "entry_reference": EntryReference.PRICE_ACTION_RETEST,
        "stop_reference": StopReference.LATEST_SWING,
        "target_reference": TargetReference.CAMARILLA_LEVEL,
        "block_reason": BlockReason.NONE,
        "market_bias": MarketBias.BULLISH,
        "market_phase": MarketPhase.TRENDING_UP,
        "confidence": ReasoningConfidence.HIGH,
        "trading_suitability": TradingSuitability.SUITABLE,
        "rationale": ("strategy",),
    }
    values.update(overrides)
    return StrategyDecisionState(**values)


def snapshot(**overrides):
    values = {
        "symbol": "NIFTY",
        "timeframe": "1m",
        "timestamp": TS,
        "strategy": strategy(),
        "policy": policy(),
        "account": account(),
        "trade_plan": trade_plan(),
    }
    values.update(overrides)
    return RiskSnapshot(**values)


def engine(symbol=" nifty ", timeframe=" 1m "):
    return RiskEngine(EventBus(), symbol, timeframe)


def feed(risk_engine, risk_snapshot=None):
    return risk_engine.update(risk_snapshot or snapshot())


def assert_rejected_preserves_state(risk_engine, bad_snapshot, expected_error=ValueError):
    old_snapshot = risk_engine.snapshot
    old_state = risk_engine.state
    old_data = risk_engine.data
    old_ready = risk_engine.is_ready()
    events = []
    risk_engine._event_bus.subscribe(RISK_UPDATED, events.append)
    assert_raises(expected_error, lambda: risk_engine.update(bad_snapshot))
    assert risk_engine.snapshot == old_snapshot
    assert risk_engine.state == old_state
    assert risk_engine.data == old_data
    assert risk_engine.is_ready() == old_ready
    assert events == []


def result(**overrides):
    return RiskCalculator.calculate(snapshot(**overrides))


def assert_rejection(reason, **overrides):
    state = result(**overrides)
    assert state.decision is RiskDecision.REJECTED
    assert state.risk_tier is RiskTier.BLOCKED
    assert state.rejection_reason is reason
    assert state.approved_lots == 0
    assert state.approved_quantity == 0
    assert state.estimated_risk_amount == 0.0
    assert state.estimated_reward_amount == 0.0
    assert state.rationale[-1] == f"rejected_{reason.value}"
    return state


def test_enum_values_models_slots_exports_and_snapshot_normalization():
    assert RiskDecision.APPROVED.value == "approved"
    assert RiskTier.REDUCED.value == "reduced"
    assert RiskRejectionReason.REQUESTED_SIZE_EXCEEDS_LIMIT.value == "requested_size_exceeds_limit"
    assert RiskReductionReason.BOTH.value == "both"

    snap = snapshot(symbol=" nifty ", timeframe=" 1m ")
    state = RiskCalculator.calculate(snap)
    assert snap.symbol == "NIFTY"
    assert snap.timeframe == "1m"
    assert isinstance(state, RiskDecisionState)
    assert not hasattr(snap, "__dict__")
    assert not hasattr(state, "__dict__")
    assert_raises(FrozenInstanceError, lambda: setattr(snap, "symbol", "BANKNIFTY"))
    assert_raises(FrozenInstanceError, lambda: setattr(state, "decision", RiskDecision.REJECTED))

    from engines.risk import __all__
    assert __all__ == [
        "RiskEngine",
        "RiskCalculator",
        "RiskPolicy",
        "AccountRiskState",
        "TradeRiskPlan",
        "RiskSnapshot",
        "RiskDecisionState",
        "RiskDecision",
        "RiskTier",
        "RiskRejectionReason",
        "RiskReductionReason",
    ]


def test_policy_validation_and_disabled_reduction_thresholds():
    risk = engine()
    feed(risk)
    later = TS + timedelta(minutes=1)
    invalids = [
        policy(max_risk_percent=0),
        policy(max_risk_percent=-1),
        policy(max_risk_percent=101),
        policy(reduced_risk_percent=3),
        policy(max_daily_loss_percent=0),
        policy(max_daily_loss_percent=101),
        policy(max_consecutive_losses=0),
        policy(reduced_after_consecutive_losses=3),
        policy(max_trades_per_day=0),
        policy(reduced_after_trades=5),
        policy(max_lots=0),
        policy(minimum_reward_risk=0),
        policy(max_risk_percent=True),
        policy(max_consecutive_losses=True),
    ]
    for bad in invalids:
        assert_rejected_preserves_state(risk, snapshot(timestamp=later, strategy=strategy(timestamp=later), policy=bad))

    disabled = policy(reduced_after_consecutive_losses=0, reduced_after_trades=0)
    reduced_state = result(policy=disabled, account=account(consecutive_losses=2, trades_today=3))
    assert reduced_state.risk_tier is RiskTier.STANDARD
    assert reduced_state.reduction_reason is RiskReductionReason.NONE
    assert reduced_state.applied_risk_percent == 2.0


def test_account_and_trade_plan_validation():
    risk = engine()
    feed(risk)
    later = TS + timedelta(minutes=1)
    for bad_account in (
        account(account_equity=0),
        account(account_equity=-1),
        account(trades_today=-1),
        account(consecutive_losses=-1),
        account(trades_today=True),
        account(consecutive_losses=True),
    ):
        assert_rejected_preserves_state(risk, snapshot(timestamp=later, strategy=strategy(timestamp=later), account=bad_account))

    plus = result(account=account(realized_pnl_today=500)).remaining_daily_loss_capacity
    minus = result(account=account(realized_pnl_today=-500)).remaining_daily_loss_capacity
    assert plus == 5000.0
    assert minus == 4500.0

    for bad_plan in (
        trade_plan(entry_price=0),
        trade_plan(stop_price=float("nan")),
        trade_plan(target_price=float("inf")),
        trade_plan(lot_size=0),
        trade_plan(requested_lots=0),
        trade_plan(entry_price=True),
        trade_plan(lot_size=True),
    ):
        assert_rejected_preserves_state(risk, snapshot(timestamp=later, strategy=strategy(timestamp=later), trade_plan=bad_plan))


def test_directional_structure_and_reward_risk():
    bullish = result(trade_plan=trade_plan(entry_price=100, stop_price=90, target_price=120))
    assert bullish.stop_distance == 10
    assert bullish.target_distance == 20
    assert bullish.reward_risk_ratio == 2.0

    bearish_strategy = strategy(direction=TradeDirection.BEARISH, market_bias=MarketBias.BEARISH)
    bearish = result(strategy=bearish_strategy, trade_plan=trade_plan(entry_price=100, stop_price=110, target_price=82))
    assert bearish.stop_distance == 10
    assert bearish.target_distance == 18
    assert bearish.reward_risk_ratio == 1.8

    rounded = result(trade_plan=trade_plan(entry_price=100, stop_price=94, target_price=110))
    assert rounded.reward_risk_ratio == 1.6667
    assert_rejection(RiskRejectionReason.REWARD_RISK_BELOW_MINIMUM, trade_plan=trade_plan(entry_price=100, stop_price=90, target_price=110))
    assert result(policy=policy(minimum_reward_risk=1.0), trade_plan=trade_plan(entry_price=100, stop_price=90, target_price=110)).decision is RiskDecision.APPROVED

    assert_rejection(RiskRejectionReason.INVALID_TRADE_DIRECTION, strategy=strategy(direction=TradeDirection.NONE))
    assert_rejection(RiskRejectionReason.INVALID_PRICE_STRUCTURE, trade_plan=trade_plan(stop_price=100))
    assert_rejection(RiskRejectionReason.INVALID_PRICE_STRUCTURE, trade_plan=trade_plan(target_price=100))
    assert_rejection(RiskRejectionReason.INVALID_PRICE_STRUCTURE, strategy=bearish_strategy, trade_plan=trade_plan(stop_price=99, target_price=80))
    assert_rejection(RiskRejectionReason.INVALID_PRICE_STRUCTURE, strategy=bearish_strategy, trade_plan=trade_plan(stop_price=110, target_price=101))


def test_strategy_blocking_and_engine_strategy_validation():
    no_trade = strategy(
        decision=StrategyDecision.NO_TRADE,
        direction=TradeDirection.NONE,
        setup_quality=SetupQuality.REJECTED,
        entry_reference=EntryReference.NONE,
        stop_reference=StopReference.NONE,
        target_reference=TargetReference.NONE,
        block_reason=BlockReason.LOW_CONFIDENCE,
    )
    assert_rejection(RiskRejectionReason.STRATEGY_NO_TRADE, strategy=no_trade)

    risk = engine()
    feed(risk)
    later = TS + timedelta(minutes=1)
    assert_rejected_preserves_state(risk, snapshot(timestamp=later, strategy=strategy(symbol="BANKNIFTY", timestamp=later)))
    assert_rejected_preserves_state(risk, snapshot(timestamp=later, strategy=strategy(timeframe="5m", timestamp=later)))
    assert_rejected_preserves_state(risk, snapshot(timestamp=later, strategy=strategy(timestamp=later + timedelta(seconds=1))))
    assert_rejected_preserves_state(risk, snapshot(timestamp=later, strategy=strategy(timestamp=later, direction=TradeDirection.NONE)))
    assert_rejected_preserves_state(risk, snapshot(timestamp=later, strategy=strategy(timestamp=later, entry_reference=EntryReference.NONE)))
    assert_rejected_preserves_state(risk, snapshot(timestamp=later, strategy=object()))


def test_daily_loss_consecutive_loss_trade_count_and_reductions():
    assert result(account=account(realized_pnl_today=1000)).remaining_daily_loss_capacity == 5000.0
    assert result(account=account(realized_pnl_today=-1000)).remaining_daily_loss_capacity == 4000.0
    assert_rejection(RiskRejectionReason.DAILY_LOSS_LIMIT_REACHED, account=account(realized_pnl_today=-5000))
    assert_rejection(RiskRejectionReason.DAILY_LOSS_LIMIT_REACHED, account=account(realized_pnl_today=-6000))

    assert result(account=account(consecutive_losses=1)).risk_tier is RiskTier.STANDARD
    loss_reduced = result(account=account(consecutive_losses=2), trade_plan=trade_plan(requested_lots=1))
    assert loss_reduced.risk_tier is RiskTier.REDUCED
    assert loss_reduced.reduction_reason is RiskReductionReason.RECENT_LOSSES
    assert_rejection(RiskRejectionReason.CONSECUTIVE_LOSS_LIMIT_REACHED, account=account(consecutive_losses=3))

    assert result(account=account(trades_today=2)).risk_tier is RiskTier.STANDARD
    trade_reduced = result(account=account(trades_today=3), trade_plan=trade_plan(requested_lots=1))
    assert trade_reduced.risk_tier is RiskTier.REDUCED
    assert trade_reduced.reduction_reason is RiskReductionReason.DAILY_DRAWDOWN
    assert_rejection(RiskRejectionReason.DAILY_TRADE_LIMIT_REACHED, account=account(trades_today=5))

    both = result(account=account(consecutive_losses=2, trades_today=3), trade_plan=trade_plan(requested_lots=1))
    assert both.risk_tier is RiskTier.REDUCED
    assert both.reduction_reason is RiskReductionReason.BOTH
    assert "reduced_both" in both.rationale


def test_position_size_one_point_per_unit_assumption_and_oversizing():
    """One price point times one unit is treated as one monetary unit in V1."""
    approved = result()
    assert approved.account_equity == 100000.0
    assert approved.daily_loss_limit_amount == 5000.0
    assert approved.risk_budget == 2000.0
    assert approved.maximum_permitted_lots == 2
    assert approved.approved_lots == 2
    assert approved.approved_quantity == 150
    assert approved.estimated_risk_amount == 1500.0
    assert approved.estimated_reward_amount == 3000.0
    assert approved.rationale == (
        "strategy_trade_eligible",
        "direction_bullish",
        "risk_tier_standard",
        "risk_percent_2.0",
        "reward_risk_2.0",
        "requested_lots_2",
        "approved_lots_2",
    )

    capped = result(policy=policy(max_lots=1), trade_plan=trade_plan(requested_lots=1))
    assert capped.maximum_permitted_lots == 1
    zero = assert_rejection(RiskRejectionReason.INSUFFICIENT_RISK_BUDGET, trade_plan=trade_plan(entry_price=100, stop_price=50, target_price=200))
    assert zero.maximum_permitted_lots == 0
    oversized = assert_rejection(RiskRejectionReason.REQUESTED_SIZE_EXCEEDS_LIMIT, trade_plan=trade_plan(requested_lots=3))
    assert oversized.maximum_permitted_lots == 2
    assert oversized.estimated_risk_amount == 0.0
    reduced_capacity = result(account=account(realized_pnl_today=-4500), trade_plan=trade_plan(requested_lots=1))
    assert reduced_capacity.risk_budget == 500.0
    assert reduced_capacity.maximum_permitted_lots == 0
    assert reduced_capacity.rejection_reason is RiskRejectionReason.INSUFFICIENT_RISK_BUDGET


def test_blocking_priority_is_deterministic():
    no_trade = strategy(decision=StrategyDecision.NO_TRADE, direction=TradeDirection.NONE)
    assert_rejection(RiskRejectionReason.STRATEGY_NO_TRADE, strategy=no_trade, trade_plan=trade_plan(stop_price=100))
    assert_rejection(RiskRejectionReason.INVALID_TRADE_DIRECTION, strategy=strategy(direction=TradeDirection.NONE), trade_plan=trade_plan(stop_price=100), account=account(realized_pnl_today=-5000))
    assert_rejection(RiskRejectionReason.INVALID_PRICE_STRUCTURE, trade_plan=trade_plan(stop_price=100), account=account(realized_pnl_today=-5000))
    assert_rejection(RiskRejectionReason.DAILY_LOSS_LIMIT_REACHED, account=account(realized_pnl_today=-5000, consecutive_losses=3, trades_today=5), trade_plan=trade_plan(target_price=105))
    assert_rejection(RiskRejectionReason.CONSECUTIVE_LOSS_LIMIT_REACHED, account=account(consecutive_losses=3, trades_today=5), trade_plan=trade_plan(target_price=105))
    assert_rejection(RiskRejectionReason.DAILY_TRADE_LIMIT_REACHED, account=account(trades_today=5), trade_plan=trade_plan(target_price=105))
    assert_rejection(RiskRejectionReason.REWARD_RISK_BELOW_MINIMUM, trade_plan=trade_plan(target_price=105))
    assert_rejection(RiskRejectionReason.INSUFFICIENT_RISK_BUDGET, policy=policy(minimum_reward_risk=1.0), trade_plan=trade_plan(entry_price=100, stop_price=1, target_price=250, requested_lots=99))


def test_engine_lifecycle_events_duplicates_corrections_reset_and_independence():
    bus = EventBus()
    events = []
    risk = RiskEngine(bus, "NIFTY", "1m")
    bus.subscribe(RISK_UPDATED, lambda state: events.append((state, risk.state, risk.data, risk.is_ready())))

    first_snapshot = snapshot()
    first = risk.update(first_snapshot)
    duplicate = risk.update(first_snapshot)
    correction = risk.update(snapshot(account=account(realized_pnl_today=-1000)))
    later = TS + timedelta(minutes=1)
    newer = risk.process(snapshot(timestamp=later, strategy=strategy(timestamp=later)))

    assert first.decision is RiskDecision.APPROVED
    assert risk.snapshot is first_snapshot or risk.state is newer
    assert risk.data is risk.state
    assert risk.is_ready()
    assert events[0] == (first, first, first, True)
    assert duplicate is first
    assert correction is not first
    assert newer is risk.state
    assert len(events) == 3
    assert_rejected_preserves_state(risk, snapshot(timestamp=TS - timedelta(minutes=1)))

    aware = RiskEngine(EventBus(), "NIFTY", "1m")
    aware_ts = TS.replace(tzinfo=timezone.utc)
    aware.update(snapshot(timestamp=aware_ts, strategy=strategy(timestamp=aware_ts)))
    assert_rejected_preserves_state(aware, snapshot(timestamp=TS, strategy=strategy(timestamp=TS)))

    risk.reset()
    assert risk.snapshot is None and risk.state is None and risk.data is None and not risk.is_ready()
    early = TS - timedelta(minutes=5)
    assert risk.update(snapshot(timestamp=early, strategy=strategy(timestamp=early))).timestamp == early
    risk.clear()
    assert risk.snapshot is None and risk.state is None and risk.data is None and not risk.is_ready()

    first_engine = RiskEngine(EventBus(), "NIFTY", "1m")
    second_engine = RiskEngine(EventBus(), "BANKNIFTY", "1m")
    first_state = first_engine.update(snapshot())
    bank_strategy = strategy(symbol="BANKNIFTY")
    second_state = second_engine.update(snapshot(symbol="BANKNIFTY", strategy=bank_strategy))
    first_engine.reset()
    assert first_engine.state is None
    assert second_engine.state == second_state
    assert second_engine.state != first_state


def test_wrong_snapshot_context_and_upstream_immutability():
    risk = engine()
    feed(risk)
    assert_rejected_preserves_state(risk, object(), TypeError)
    assert_rejected_preserves_state(risk, snapshot(symbol="BANKNIFTY"))
    assert_rejected_preserves_state(risk, snapshot(timeframe="5m"))
    assert_rejected_preserves_state(risk, snapshot(timestamp="bad"))
    assert_raises(ValueError, lambda: RiskEngine(EventBus(), "", "1m"))
    assert_raises(ValueError, lambda: RiskEngine(EventBus(), 1, "1m"))
    assert_raises(ValueError, lambda: RiskEngine(EventBus(), "NIFTY", ""))

    strat = strategy()
    pol = policy()
    acct = account()
    plan = trade_plan()
    snap = snapshot(strategy=strat, policy=pol, account=acct, trade_plan=plan)
    before = (strat, pol, acct, plan, snap)
    state = RiskCalculator.calculate(snap)
    assert (strat, pol, acct, plan, snap) == before
    assert state.rationale[:3] == ("strategy_trade_eligible", "direction_bullish", "risk_tier_standard")
