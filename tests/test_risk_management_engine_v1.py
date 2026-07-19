from dataclasses import FrozenInstanceError
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from application.models import RuntimeConfiguration
from application.orchestrator import ApplicationOrchestrator
from core.event_bus import EventBus
from core.events import RISK_APPROVED, RISK_EVALUATED, RISK_LOCKED, RISK_REJECTED, RISK_STATE_UPDATED
from engines.order_management.models import OrderRequest, OrderSide, OrderType, ProductType
from engines.risk.enums import RiskDecisionStatus, RiskLifecycleState, RiskReasonCode, RiskSeverity
from engines.risk.models import AccountRiskState, InstrumentRiskExposure, RiskDecisionRecord, RiskEngineSnapshot, RiskFinding, RiskPolicy, TradeRiskPlan
from engines.risk.risk_engine import RiskEngine
from engines.strategy.enums import TradeDirection


IST = ZoneInfo("Asia/Kolkata")
TS = datetime(2026, 7, 13, 10, 0, tzinfo=IST)


def engine():
    return RiskEngine(EventBus(), "NIFTY", "1m")


def policy(**overrides):
    values = {
        "risk_per_trade_percentage": 1.0,
        "maximum_risk_per_trade_amount": 1000.0,
        "maximum_daily_loss_amount": 3000.0,
        "maximum_daily_loss_percentage": 5.0,
        "maximum_trades_per_session": 3,
        "maximum_consecutive_losses": 2,
        "cooldown_minutes_after_loss": 15,
        "revenge_trade_window_minutes": 10,
        "minimum_reward_to_risk": 1.5,
        "maximum_stop_distance_percentage": 20.0,
        "minimum_stop_distance_percentage": 0.05,
        "maximum_total_open_risk": 5000.0,
        "maximum_instrument_open_risk": 2500.0,
        "maximum_quantity": 300,
        "maximum_lots": 2,
        "lot_sizes_by_instrument": {"NIFTY": 75, "BANKNIFTY": 35, "SENSEX": 20},
    }
    values.update(overrides)
    return RiskPolicy(**values)


def account(**overrides):
    values = {
        "account_equity": 100000.0,
        "realized_pnl_today": 0.0,
        "trades_today": 0,
        "consecutive_losses": 0,
        "starting_capital": 100000.0,
        "available_capital": 100000.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "daily_pnl": 0.0,
        "open_risk": 0.0,
        "margin_used": 0.0,
        "session_date": TS.date(),
    }
    values.update(overrides)
    return AccountRiskState(**values)


def plan(**overrides):
    values = {
        "instrument": "NIFTY",
        "direction": TradeDirection.BULLISH,
        "entry_price": 100.0,
        "stop_loss_price": 95.0,
        "target_price": 110.0,
        "lot_size": 75,
        "requested_lots": 2,
        "timestamp": TS,
        "manual_approval": True,
    }
    values.update(overrides)
    return TradeRiskPlan(**values)


def evaluate(**overrides):
    risk = overrides.pop("risk_engine", engine())
    return risk.evaluate(
        policy=overrides.pop("policy", policy()),
        account=overrides.pop("account", account()),
        trade_plan=overrides.pop("trade_plan", plan()),
        timestamp=overrides.pop("timestamp", TS),
    )


def assert_reason(decision, status, reason):
    assert decision.status is status
    assert decision.primary_reason is reason
    assert decision.approved is (status in {RiskDecisionStatus.APPROVED, RiskDecisionStatus.APPROVED_WITH_REDUCED_SIZE})
    return decision


def test_policy_models_are_immutable_and_validation_rejects_bad_numeric_inputs():
    pol = policy()
    decision = evaluate(policy=pol)
    assert isinstance(decision, RiskDecisionRecord)
    assert pol.maximum_lots == 2
    with pytest.raises(FrozenInstanceError):
        pol.maximum_lots = 3
    assert isinstance(pol.lot_sizes_by_instrument, tuple)
    original = {"NIFTY": 75}
    immutable_policy = policy(lot_sizes_by_instrument=original)
    original["NIFTY"] = 1
    assert immutable_policy.lot_size_for("NIFTY") == 75
    with pytest.raises(TypeError):
        immutable_policy.lot_sizes_by_instrument["NIFTY"] = 1

    for bad_policy in (
        lambda: policy(risk_per_trade_percentage=0),
        lambda: policy(risk_per_trade_percentage=float("nan")),
        lambda: policy(maximum_lots=0),
        lambda: policy(lot_sizes_by_instrument={"NIFTY": 0}),
        lambda: policy(minimum_stop_distance_percentage=5.0, maximum_stop_distance_percentage=1.0),
        lambda: policy(trading_start_time=time(14, 30), last_entry_time=time(9, 15)),
    ):
        with pytest.raises((TypeError, ValueError)):
            bad_policy()

    for bad_account in (
        lambda: account(available_capital=-1),
        lambda: account(open_risk=-1),
        lambda: account(margin_used=float("inf")),
        lambda: account(session_date="2026-07-13"),
    ):
        with pytest.raises((TypeError, ValueError)):
            bad_account()

    risk = engine()
    with pytest.raises(ValueError):
        risk.evaluate(policy=policy(), account=account(), trade_plan=plan(timestamp=TS.replace(tzinfo=None)), timestamp=TS.replace(tzinfo=None))
    with pytest.raises(ValueError):
        risk.evaluate(policy=policy(), account=account(), trade_plan=plan(direction="sideways"), timestamp=TS)
    for bad_plan in (
        lambda: plan(entry_price=float("nan")),
        lambda: plan(stop_loss_price=float("inf")),
        lambda: plan(lot_size=0),
        lambda: plan(existing_position_quantity=-1),
        lambda: plan(is_fomo_entry="yes"),
    ):
        with pytest.raises((TypeError, ValueError)):
            bad_plan()


def test_long_short_sizing_strictest_limit_lot_rounding_and_reduced_size():
    long_decision = evaluate()
    assert_reason(long_decision, RiskDecisionStatus.APPROVED, RiskReasonCode.APPROVED)
    assert long_decision.risk_per_unit == 5.0
    assert long_decision.reward_per_unit == 10.0
    assert long_decision.reward_to_risk == 2.0
    assert long_decision.approved_quantity == 150
    assert long_decision.approved_lots == 2
    assert long_decision.approved_trade_risk == 750.0

    short_decision = evaluate(trade_plan=plan(direction="short", entry_price=100, stop_loss_price=105, target_price=90))
    assert short_decision.direction is TradeDirection.BEARISH
    assert short_decision.risk_per_unit == 5.0
    assert short_decision.reward_per_unit == 10.0

    reduced = evaluate(trade_plan=plan(requested_lots=5), policy=policy(maximum_risk_per_trade_amount=800.0, maximum_quantity=1000))
    assert_reason(reduced, RiskDecisionStatus.APPROVED_WITH_REDUCED_SIZE, RiskReasonCode.SIZE_REDUCED)
    assert reduced.approved_quantity == 150
    assert reduced.requested_quantity == 375
    assert reduced.approved_quantity < reduced.requested_quantity

    no_lot = evaluate(policy=policy(maximum_risk_per_trade_amount=100.0))
    assert_reason(no_lot, RiskDecisionStatus.REJECTED, RiskReasonCode.RISK_PER_TRADE_EXCEEDED)
    assert no_lot.approved_quantity == 0


def test_stop_target_reward_and_quantity_validation_reasons():
    assert_reason(evaluate(trade_plan=plan(stop_loss_price=None)), RiskDecisionStatus.INVALID, RiskReasonCode.MISSING_STOP_LOSS)
    assert_reason(evaluate(trade_plan=plan(target_price=None)), RiskDecisionStatus.INVALID, RiskReasonCode.MISSING_TARGET)
    assert_reason(evaluate(trade_plan=plan(stop_loss_price=99.99)), RiskDecisionStatus.REJECTED, RiskReasonCode.STOP_TOO_TIGHT)
    assert_reason(evaluate(trade_plan=plan(stop_loss_price=50)), RiskDecisionStatus.REJECTED, RiskReasonCode.STOP_TOO_WIDE)
    assert_reason(evaluate(trade_plan=plan(target_price=106)), RiskDecisionStatus.REJECTED, RiskReasonCode.INSUFFICIENT_REWARD_RISK)
    assert_reason(evaluate(trade_plan=plan(target_price=107.5)), RiskDecisionStatus.APPROVED, RiskReasonCode.APPROVED)
    with pytest.raises(ValueError):
        evaluate(trade_plan=plan(entry_price=0))
    with pytest.raises(ValueError):
        evaluate(trade_plan=plan(requested_quantity=0))


def test_session_limits_locks_cooldown_and_profit_protection_are_deterministic():
    risk = engine()
    assert risk.start().lifecycle_state is RiskLifecycleState.READY
    for _ in range(3):
        risk.record_trade_opened(instrument="NIFTY", risk_amount=100.0, timestamp=TS)
    assert_reason(evaluate(risk_engine=risk), RiskDecisionStatus.LOCKED, RiskReasonCode.MAX_TRADES_REACHED)

    daily_loss = evaluate(account=account(daily_pnl=-3000.0))
    assert_reason(daily_loss, RiskDecisionStatus.LOCKED, RiskReasonCode.DAILY_LOSS_LIMIT_REACHED)

    profit_risk = engine()
    assert_reason(evaluate(risk_engine=profit_risk, account=account(daily_pnl=2500.0), policy=policy(daily_profit_lock_trigger=2000.0, daily_profit_giveback_limit=500.0)), RiskDecisionStatus.APPROVED, RiskReasonCode.APPROVED)
    giveback = evaluate(risk_engine=profit_risk, account=account(daily_pnl=1900.0), policy=policy(daily_profit_lock_trigger=2000.0, daily_profit_giveback_limit=500.0))
    assert_reason(giveback, RiskDecisionStatus.LOCKED, RiskReasonCode.DAILY_PROFIT_LOCK_ACTIVE)

    cooldown = engine()
    cooldown.evaluate(policy=policy(maximum_consecutive_losses=2), account=account(), trade_plan=plan(), timestamp=TS)
    cooldown.record_trade_closed(instrument="NIFTY", realized_pnl=-100.0, timestamp=TS)
    below_threshold = evaluate(risk_engine=cooldown, policy=policy(maximum_consecutive_losses=2), timestamp=TS + timedelta(minutes=1), trade_plan=plan(timestamp=TS + timedelta(minutes=1)))
    assert below_threshold.status is RiskDecisionStatus.APPROVED
    cooldown.record_trade_closed(instrument="NIFTY", realized_pnl=-100.0, timestamp=TS + timedelta(minutes=2))
    locked = evaluate(risk_engine=cooldown, policy=policy(maximum_consecutive_losses=2), timestamp=TS + timedelta(minutes=5), trade_plan=plan(timestamp=TS + timedelta(minutes=5)))
    assert_reason(locked, RiskDecisionStatus.LOCKED, RiskReasonCode.CONSECUTIVE_LOSS_COOLDOWN)
    boundary = TS + timedelta(minutes=17)
    approved = evaluate(risk_engine=cooldown, policy=policy(maximum_consecutive_losses=2), timestamp=boundary, trade_plan=plan(timestamp=boundary))
    assert approved.status is RiskDecisionStatus.APPROVED
    cooldown.record_trade_closed(instrument="NIFTY", realized_pnl=100.0, timestamp=boundary)
    assert cooldown.engine_snapshot().consecutive_losses == 0
    cooldown.record_trade_closed(instrument="NIFTY", realized_pnl=-100.0, timestamp=boundary + timedelta(minutes=1))
    assert cooldown.engine_snapshot().consecutive_losses == 1

    revenge = engine()
    revenge.evaluate(policy=policy(maximum_consecutive_losses=2), account=account(), trade_plan=plan(), timestamp=TS)
    revenge.record_trade_closed(instrument="NIFTY", realized_pnl=-100.0, timestamp=TS)
    revenge_plan = plan(timestamp=TS + timedelta(minutes=1), is_revenge_entry=True)
    revenge_locked = evaluate(risk_engine=revenge, policy=policy(maximum_consecutive_losses=2), timestamp=revenge_plan.timestamp, trade_plan=revenge_plan)
    assert_reason(revenge_locked, RiskDecisionStatus.LOCKED, RiskReasonCode.REVENGE_TRADING_LOCKOUT)


def test_discipline_rules_manual_emergency_priority_and_trading_windows():
    missing_manual = evaluate(trade_plan=plan(manual_approval=False))
    assert_reason(missing_manual, RiskDecisionStatus.LOCKED, RiskReasonCode.MANUAL_APPROVAL_REQUIRED)
    assert missing_manual.approved_quantity == 0
    assert evaluate(trade_plan=plan(manual_approval=True)).status is RiskDecisionStatus.APPROVED
    assert evaluate(policy=policy(manual_approval_required=False), trade_plan=plan(manual_approval=False)).status is RiskDecisionStatus.APPROVED
    assert_reason(evaluate(trade_plan=plan(is_fomo_entry=True)), RiskDecisionStatus.REJECTED, RiskReasonCode.FOMO_ENTRY)
    assert_reason(evaluate(trade_plan=plan(is_averaging_entry=True)), RiskDecisionStatus.REJECTED, RiskReasonCode.AVERAGING_DOWN_BLOCKED)
    duplicate = evaluate(trade_plan=plan(existing_position_direction=TradeDirection.BULLISH, existing_position_quantity=75))
    assert_reason(duplicate, RiskDecisionStatus.REJECTED, RiskReasonCode.DUPLICATE_POSITION)

    early = TS.replace(hour=9, minute=0)
    assert_reason(evaluate(timestamp=early, trade_plan=plan(timestamp=early)), RiskDecisionStatus.REJECTED, RiskReasonCode.OUTSIDE_TRADING_WINDOW)
    late = TS.replace(hour=14, minute=31)
    assert_reason(evaluate(timestamp=late, trade_plan=plan(timestamp=late)), RiskDecisionStatus.REJECTED, RiskReasonCode.LATE_ENTRY)
    mismatch = evaluate(account=account(session_date=date(2026, 7, 14)))
    assert_reason(mismatch, RiskDecisionStatus.INVALID, RiskReasonCode.OUTSIDE_TRADING_WINDOW)

    locked = engine()
    locked.evaluate(policy=policy(), account=account(), trade_plan=plan(), timestamp=TS)
    locked.activate_manual_lock()
    assert_reason(evaluate(risk_engine=locked), RiskDecisionStatus.LOCKED, RiskReasonCode.MANUAL_LOCK_ACTIVE)
    locked.activate_emergency_lock()
    assert_reason(evaluate(risk_engine=locked), RiskDecisionStatus.LOCKED, RiskReasonCode.EMERGENCY_LOCK_ACTIVE)


def test_exposure_limits_and_open_risk_are_calculated():
    risk = engine()
    risk.record_trade_opened(instrument="NIFTY", risk_amount=2400.0, timestamp=TS)
    instrument_limit = evaluate(risk_engine=risk)
    assert_reason(instrument_limit, RiskDecisionStatus.REJECTED, RiskReasonCode.INSTRUMENT_EXPOSURE_EXCEEDED)

    total = engine()
    total.record_trade_opened(instrument="BANKNIFTY", risk_amount=4800.0, timestamp=TS)
    total_limit = evaluate(risk_engine=total, policy=policy(maximum_instrument_open_risk=5000.0))
    assert_reason(total_limit, RiskDecisionStatus.REJECTED, RiskReasonCode.TOTAL_OPEN_RISK_EXCEEDED)

    account_risk = evaluate(account=account(open_risk=4600.0), policy=policy(maximum_total_open_risk=5000.0, maximum_instrument_open_risk=5000.0))
    assert_reason(account_risk, RiskDecisionStatus.APPROVED_WITH_REDUCED_SIZE, RiskReasonCode.SIZE_REDUCED)
    assert account_risk.total_open_risk_after_trade == 4975.0
    at_limit = evaluate(account=account(open_risk=5000.0), policy=policy(maximum_total_open_risk=5000.0, maximum_instrument_open_risk=5000.0))
    assert_reason(at_limit, RiskDecisionStatus.REJECTED, RiskReasonCode.TOTAL_OPEN_RISK_EXCEEDED)
    session_wins = engine()
    session_wins.record_trade_opened(instrument="BANKNIFTY", risk_amount=3000.0, timestamp=TS)
    session_decision = evaluate(risk_engine=session_wins, account=account(open_risk=1000.0), policy=policy(maximum_total_open_risk=5000.0, maximum_instrument_open_risk=5000.0))
    assert session_decision.total_open_risk_after_trade == 3750.0
    reconstructed = engine()
    bypass = evaluate(risk_engine=reconstructed, account=account(open_risk=4800.0), policy=policy(maximum_total_open_risk=5000.0, maximum_instrument_open_risk=5000.0))
    assert_reason(bypass, RiskDecisionStatus.REJECTED, RiskReasonCode.TOTAL_OPEN_RISK_EXCEEDED)

    assert_reason(evaluate(account=account(available_capital=0.0)), RiskDecisionStatus.REJECTED, RiskReasonCode.INSUFFICIENT_CAPITAL)


def test_reset_snapshot_bounded_findings_and_deduplication():
    risk = engine()
    for _ in range(3):
        evaluate(risk_engine=risk, trade_plan=plan(is_fomo_entry=True))
    snap = risk.engine_snapshot()
    assert isinstance(snap, RiskEngineSnapshot)
    assert snap.rejected_count == 3
    fomo = [item for item in snap.findings if item.code is RiskReasonCode.FOMO_ENTRY][0]
    assert fomo.occurrence_count == 3
    assert len(snap.findings) <= 50
    risk.activate_emergency_lock()
    risk.activate_manual_lock()
    reset = risk.reset_session(date(2026, 7, 14))
    assert reset.trading_date == date(2026, 7, 14)
    assert reset.manual_lock_active is False
    assert reset.emergency_lock_active is True
    assert reset.last_decision is None
    assert reset.broker_order_calls == 0


def test_immutable_exposure_models_snapshot_and_auto_rollover_clear_manual_lock_only():
    exposure_source = {"NIFTY": 100.0}
    session = engine()
    session.record_trade_opened(instrument="NIFTY", risk_amount=100.0, timestamp=TS)
    snap = session.engine_snapshot()
    assert isinstance(snap.instrument_open_risk, tuple)
    exposure_source["NIFTY"] = 1.0
    immutable_exposure = InstrumentRiskExposure("NIFTY", 100.0)
    with pytest.raises(FrozenInstanceError):
        immutable_exposure.open_risk = 1.0
    copied = tuple(snap.instrument_open_risk)
    copied += (InstrumentRiskExposure("BANKNIFTY", 1.0),)
    assert session.engine_snapshot().instrument_open_risk == snap.instrument_open_risk

    rollover = engine()
    rollover.activate_manual_lock()
    rollover.activate_emergency_lock()
    later = TS + timedelta(days=1)
    locked = evaluate(risk_engine=rollover, timestamp=later, trade_plan=plan(timestamp=later), account=account(session_date=later.date()))
    assert_reason(locked, RiskDecisionStatus.LOCKED, RiskReasonCode.EMERGENCY_LOCK_ACTIVE)
    rolled = rollover.engine_snapshot()
    assert rolled.manual_lock_active is False
    assert rolled.emergency_lock_active is True


def test_fingerprints_and_ordered_findings_are_deterministic():
    first = evaluate()
    second = evaluate()
    assert first.policy_fingerprint == second.policy_fingerprint
    assert first.plan_fingerprint == second.plan_fingerprint
    assert first.input_fingerprint == second.input_fingerprint
    assert first.decision_id == second.decision_id
    assert tuple(item.code for item in first.findings) == tuple(item.code for item in second.findings)
    assert first.policy_fingerprint != evaluate(policy=policy(maximum_lots=1)).policy_fingerprint
    assert first.plan_fingerprint != evaluate(trade_plan=plan(target_price=112.0)).plan_fingerprint


def test_events_emit_once_per_authoritative_evaluation():
    bus = EventBus()
    risk = RiskEngine(bus, "NIFTY", "1m")
    seen = {RISK_EVALUATED: [], RISK_APPROVED: [], RISK_REJECTED: [], RISK_LOCKED: [], RISK_STATE_UPDATED: []}
    for name in seen:
        bus.subscribe(name, seen[name].append)

    risk.evaluate(policy=policy(), account=account(), trade_plan=plan(), timestamp=TS)
    risk.evaluate(policy=policy(), account=account(), trade_plan=plan(is_fomo_entry=True), timestamp=TS)
    risk.activate_manual_lock()
    risk.evaluate(policy=policy(), account=account(), trade_plan=plan(), timestamp=TS)

    assert len(seen[RISK_EVALUATED]) == 3
    assert len(seen[RISK_APPROVED]) == 1
    assert len(seen[RISK_REJECTED]) == 1
    assert len(seen[RISK_LOCKED]) == 1
    assert len(seen[RISK_STATE_UPDATED]) >= 3


def test_application_runtime_owns_authoritative_risk_and_rejected_risk_blocks_order_creation():
    app = ApplicationOrchestrator(EventBus(), RuntimeConfiguration())
    app.start()
    runtime = app.get_runtime("NIFTY")
    rejected = runtime.risk_engine.evaluate(
        policy=policy(),
        account=account(),
        trade_plan=plan(manual_approval=False),
        timestamp=TS,
    )
    assert rejected.status is RiskDecisionStatus.LOCKED
    request = OrderRequest(
        client_order_id="risk-blocked",
        symbol="NIFTY",
        exchange="NSE",
        timeframe="1m",
        timestamp=TS,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        quantity=75,
    )
    with pytest.raises(ValueError):
        app.create_order("NIFTY", request)
    assert app.broker_adapter.mode.value == "dry_run"
    assert runtime.risk_engine.engine_snapshot().broker_order_calls == 0


def test_no_duplicate_event_bus_construction_or_runtime_dangerous_symbols():
    text = open("engines/risk/risk_engine.py", encoding="utf-8").read()
    assert "EventBus(" not in text
    assert "place_order" not in text
    assert "modify_order" not in text
    assert "cancel_order" not in text
    assert "broker_adapter.place" not in text
    assert "threading" not in text
    assert "asyncio" not in text
    assert "time.sleep" not in text
    assert "clear_persistent_data=True" not in text
