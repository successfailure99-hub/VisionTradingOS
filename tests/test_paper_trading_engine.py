from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from application import ExecutionSafetyMode
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.models.candle import Candle
from core.models.tick import Tick
from dashboard.presenters import build_journal_view, build_position_view
from engines.paper_trading import (
    PaperExitType,
    PaperOrderState,
    PaperPositionState,
    PaperTradeRecord,
    PaperTradingConfiguration,
    PaperTradingEngine,
)
from engines.risk.enums import RiskDecision, RiskRejectionReason, RiskReductionReason, RiskTier
from engines.risk.models import RiskDecisionState, TradePlan
from engines.strategy.enums import TradeDirection


NOW = datetime(2026, 7, 15, 9, 20, tzinfo=UTC)


def plan(direction=TradeDirection.BULLISH, entry_type="structure_break_retest", plan_id="plan-1"):
    return TradePlan(
        plan_id=plan_id,
        instrument="NIFTY",
        created_at=NOW,
        strategy_direction=direction,
        strategy_setup="high",
        entry_type=entry_type,
        entry_price=100.0,
        stop_price=95.0 if direction is TradeDirection.BULLISH else 105.0,
        target_price=110.0 if direction is TradeDirection.BULLISH else 90.0,
        lot_size=75,
        approved_lots=1,
        approved_quantity=75,
        risk_amount=375.0,
        reward_amount=750.0,
        reward_risk=2.0,
        valid_from=NOW,
        valid_until=NOW + timedelta(minutes=15),
        status="READY",
        reasoning=("risk_approved",),
        source_strategy_id="strategy-1",
    )


def risk(direction=TradeDirection.BULLISH, approved=True):
    return RiskDecisionState(
        symbol="NIFTY",
        timeframe="1m",
        timestamp=NOW,
        decision=RiskDecision.APPROVED if approved else RiskDecision.REJECTED,
        risk_tier=RiskTier.STANDARD if approved else RiskTier.BLOCKED,
        rejection_reason=RiskRejectionReason.NONE if approved else RiskRejectionReason.STRATEGY_NO_TRADE,
        reduction_reason=RiskReductionReason.NONE,
        direction=direction,
        account_equity=100000.0,
        realized_pnl_today=0.0,
        daily_loss_limit_amount=5000.0,
        remaining_daily_loss_capacity=5000.0,
        applied_risk_percent=1.0,
        risk_budget=1000.0,
        entry_price=100.0,
        stop_price=95.0 if direction is TradeDirection.BULLISH else 105.0,
        target_price=110.0 if direction is TradeDirection.BULLISH else 90.0,
        stop_distance=5.0,
        target_distance=10.0,
        reward_risk_ratio=2.0,
        lot_size=75,
        requested_lots=1,
        maximum_permitted_lots=1,
        approved_lots=1 if approved else 0,
        approved_quantity=75 if approved else 0,
        estimated_risk_amount=375.0,
        estimated_reward_amount=750.0,
        rationale=("risk_approved",),
        plan_id="plan-1",
        plan_status="READY" if approved else "REJECTED",
        valid_until=NOW + timedelta(minutes=15),
        risk_reason="Trade plan ready" if approved else "rejected",
        trade_plan_ready=approved,
    )


def tick(price, ts=None, symbol=Instrument.NIFTY):
    return Tick(symbol, Exchange.NSE, ts or NOW, price, 1, price - 0.5, price + 0.5, 0)


def engine(**config):
    return PaperTradingEngine(
        EventBus(),
        instrument="NIFTY",
        timeframe="1m",
        safety_mode=ExecutionSafetyMode.ANALYSIS_ONLY,
        configuration=PaperTradingConfiguration(**config),
    )


def test_models_are_immutable_and_validate_required_values():
    item = engine()
    item.receive_plan(plan(), risk())
    order = item.snapshot().order
    assert order.state is PaperOrderState.PENDING
    with pytest.raises(FrozenInstanceError):
        order.quantity = 1
    with pytest.raises(ValueError):
        TradePlan(
            plan_id="bad",
            instrument="NIFTY",
            created_at=NOW,
            strategy_direction=TradeDirection.BULLISH,
            strategy_setup="high",
            entry_type="structure_break_retest",
            entry_price=100.0,
            stop_price=95.0,
            target_price=110.0,
            lot_size=75,
            approved_lots=1,
            approved_quantity=74,
            risk_amount=375.0,
            reward_amount=750.0,
            reward_risk=2.0,
            valid_from=NOW,
            valid_until=NOW + timedelta(minutes=15),
            status="READY",
            reasoning=("risk_approved",),
            source_strategy_id="strategy-1",
        )


def test_ready_plan_creates_one_pending_order_and_rejected_risk_creates_none():
    item = engine()
    item.receive_plan(plan(), risk())
    item.receive_plan(plan(), risk())
    assert item.snapshot().diagnostics.orders_created == 1
    rejected = engine()
    rejected.receive_plan(plan(), risk(approved=False))
    assert rejected.snapshot().order is None


def test_bullish_retest_entry_target_lifecycle_and_journal_summary():
    item = engine()
    item.receive_plan(plan(), risk())
    item.on_tick(tick(103, NOW + timedelta(seconds=1)))
    assert item.snapshot().order.state is PaperOrderState.PENDING
    item.on_tick(tick(100, NOW + timedelta(seconds=2)))
    assert item.snapshot().position.state is PaperPositionState.OPEN
    item.on_tick(tick(106, NOW + timedelta(seconds=3)))
    record = item.on_tick(tick(110, NOW + timedelta(seconds=4)))
    assert record.exit_type is PaperExitType.TARGET
    assert record.net_pnl == 750.0
    assert item.snapshot().position is None
    assert item.snapshot().journal_summary.record_count == 1
    assert item.snapshot().diagnostics.broker_order_calls == 0


def test_bullish_stop_gap_uses_adverse_exit_and_duplicate_stop_does_not_duplicate():
    item = engine()
    item.receive_plan(plan(), risk())
    item.on_tick(tick(103, NOW + timedelta(seconds=1)))
    item.on_tick(tick(100, NOW + timedelta(seconds=2)))
    record = item.on_tick(tick(93, NOW + timedelta(seconds=3)))
    assert record.exit_type is PaperExitType.STOP_LOSS
    assert record.exit_price == 93.0
    assert record.net_pnl == -525.0
    assert item.on_tick(tick(92, NOW + timedelta(seconds=4))) is None
    assert item.snapshot().journal_summary.record_count == 1


def test_bearish_retest_and_target_lifecycle():
    item = engine()
    bearish_plan = plan(TradeDirection.BEARISH)
    item.receive_plan(bearish_plan, risk(TradeDirection.BEARISH))
    item.on_tick(tick(97, NOW + timedelta(seconds=1)))
    item.on_tick(tick(100, NOW + timedelta(seconds=2)))
    assert item.snapshot().position.direction is TradeDirection.BEARISH
    record = item.on_tick(tick(90, NOW + timedelta(seconds=3)))
    assert record.exit_type is PaperExitType.TARGET
    assert record.net_pnl == 750.0


def test_breakout_entries_require_explicit_entry_type():
    item = engine()
    breakout = plan(entry_type="breakout_stop")
    item.receive_plan(breakout, risk())
    item.on_tick(tick(98, NOW + timedelta(seconds=1)))
    assert item.on_tick(tick(100, NOW + timedelta(seconds=2))) is None
    assert item.snapshot().position is not None


def test_same_candle_uses_stop_first_for_ambiguous_stop_and_target():
    item = engine()
    item.receive_plan(plan(), risk())
    item.on_tick(tick(103, NOW + timedelta(seconds=1)))
    item.on_tick(tick(100, NOW + timedelta(seconds=2)))
    record = item.on_candle(Candle("NIFTY", "1m", NOW, NOW + timedelta(minutes=1), 100.0, 112.0, 94.0, 101.0, 10))
    assert record.exit_type is PaperExitType.STOP_LOSS
    assert record.net_pnl == -375.0


def test_pending_cancellation_expiry_wrong_instrument_and_unsafe_mode():
    item = engine()
    item.receive_plan(plan(), risk())
    item.on_tick(tick(94, NOW + timedelta(seconds=1)))
    assert item.snapshot().order.state is PaperOrderState.CANCELLED
    assert item.snapshot().journal_summary.record_count == 0

    expired = engine()
    expired.receive_plan(plan(), risk())
    expired.on_tick(tick(101, NOW + timedelta(minutes=16)))
    assert expired.snapshot().order.state is PaperOrderState.EXPIRED

    unsafe = PaperTradingEngine(EventBus(), instrument="NIFTY", timeframe="1m", safety_mode="live", configuration=PaperTradingConfiguration())
    unsafe.receive_plan(plan(), risk())
    assert unsafe.snapshot().order is None


def test_dashboard_views_render_pending_open_and_completed_paper_state():
    from application.models import RuntimeSnapshot
    from application.enums import RuntimeInstrument, RuntimeStatus

    item = engine()
    item.receive_plan(plan(), risk())
    snap = RuntimeSnapshot(RuntimeInstrument.NIFTY, "1m", RuntimeStatus.RUNNING, tick(101), None, None, None, None, None, None, None, None, None, risk(), None, None, None, NOW, paper_trading=item.snapshot())
    pending = build_position_view(snap)
    assert pending.status == "Pending Paper Entry"
    assert pending.entry_price == 100.0

    item.on_tick(tick(103, NOW + timedelta(seconds=1)))
    item.on_tick(tick(100, NOW + timedelta(seconds=2)))
    open_snap = RuntimeSnapshot(RuntimeInstrument.NIFTY, "1m", RuntimeStatus.RUNNING, tick(104), None, None, None, None, None, None, None, None, None, risk(), None, None, None, NOW, paper_trading=item.snapshot())
    opened = build_position_view(open_snap)
    assert opened.status == "Paper Position Open"
    assert opened.has_position is True

    item.on_tick(tick(110, NOW + timedelta(seconds=3)))
    closed_snap = RuntimeSnapshot(RuntimeInstrument.NIFTY, "1m", RuntimeStatus.RUNNING, tick(110), None, None, None, None, None, None, None, None, None, risk(), None, None, None, NOW, paper_trading=item.snapshot())
    journal = build_journal_view(closed_snap)
    assert journal.records == 1
    assert journal.latest_realized_pnl == 750.0
    assert journal.latest_exit_type == "Target"
