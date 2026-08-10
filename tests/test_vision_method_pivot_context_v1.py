from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone

import pytest

from application import RuntimeSnapshot
from application.enums import RuntimeInstrument, RuntimeStatus
from application.vision_forensics import VisionForensicTrace
from core.enums.exchange import Exchange
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC
from engines.camarilla.calculator import CamarillaCalculator
from engines.cpr.calculator import CPRCalculator
from engines.runtime_adapter import (
    TradeCandidate,
    TradeCandidateDirection,
    TradeCandidateState,
)
from engines.vision_method import (
    VisionCandidateState,
    VisionPivotCombinedContext,
    VisionPivotContextConfiguration,
    VisionPivotDirectionalPrior,
    VisionPivotFlightPlanRequest,
    VisionPivotRelationship,
    VisionPivotTendency,
    VisionPivotWidthState,
    build_pivot_flight_plan,
    calculate_vision_method_snapshot,
    classify_pivot_relationship,
    classify_width,
    validate_vision_method,
)
from tests.test_vision_method_validation_v1 import NOW, snapshot


IST = timezone(timedelta(hours=5, minutes=30))


def daily(trading_date: date, high: float, low: float, close: float | None = None) -> DailyOHLC:
    close = (high + low) / 2.0 if close is None else close
    return DailyOHLC(trading_date=trading_date, open=(high + low) / 2.0, high=high, low=low, close=close)


def history() -> tuple[DailyOHLC, ...]:
    base = date(2026, 7, 21)
    return tuple(
        daily(base + timedelta(days=index), 101.0 + index, 99.0 + index, 100.0 + index)
        for index in range(7)
    )


def plan_request(
    *,
    current_source: DailyOHLC | None = None,
    historical_daily_ohlc: tuple[DailyOHLC, ...] | None = None,
    trading_date: date = date(2026, 7, 29),
    reference_date: date = date(2026, 7, 28),
    generated_at: datetime = NOW,
) -> VisionPivotFlightPlanRequest:
    source = current_source or daily(reference_date, 120.0, 100.0, 116.0)
    current_cpr = replace(CPRCalculator.calculate(source), trading_date=trading_date)
    current_camarilla = replace(CamarillaCalculator.calculate(source), trading_date=trading_date)
    return VisionPivotFlightPlanRequest(
        instrument=RuntimeInstrument.NIFTY,
        trading_date=trading_date,
        reference_session_date=reference_date,
        generated_at=generated_at,
        current_cpr=current_cpr,
        current_camarilla=current_camarilla,
        historical_daily_ohlc=history() if historical_daily_ohlc is None else historical_daily_ohlc,
    )


def test_pivot_relationship_classifies_seven_deterministic_states():
    assert classify_pivot_relationship((110.0, 112.0), (100.0, 105.0), tolerance=0.01) is VisionPivotRelationship.HIGHER_VALUE
    assert classify_pivot_relationship((103.0, 108.0), (100.0, 105.0), tolerance=0.01) is VisionPivotRelationship.OVERLAPPING_HIGHER_VALUE
    assert classify_pivot_relationship((90.0, 95.0), (100.0, 105.0), tolerance=0.01) is VisionPivotRelationship.LOWER_VALUE
    assert classify_pivot_relationship((98.0, 102.0), (100.0, 105.0), tolerance=0.01) is VisionPivotRelationship.OVERLAPPING_LOWER_VALUE
    assert classify_pivot_relationship((100.01, 105.01), (100.0, 105.0), tolerance=0.01) is VisionPivotRelationship.UNCHANGED_VALUE
    assert classify_pivot_relationship((99.0, 106.0), (100.0, 105.0), tolerance=0.01) is VisionPivotRelationship.OUTSIDE_VALUE
    assert classify_pivot_relationship((101.0, 104.0), (100.0, 105.0), tolerance=0.01) is VisionPivotRelationship.INSIDE_VALUE


def test_width_classification_uses_history_and_returns_insufficient_without_context():
    config = VisionPivotContextConfiguration(pivot_width_history_sessions=5)

    assert classify_width(0.5, (1.0, 1.0, 1.0, 1.0, 1.0), configuration=config) is VisionPivotWidthState.NARROW
    assert classify_width(1.0, (1.0, 1.0, 1.0, 1.0, 1.0), configuration=config) is VisionPivotWidthState.NORMAL
    assert classify_width(1.5, (1.0, 1.0, 1.0, 1.0, 1.0), configuration=config) is VisionPivotWidthState.WIDE
    assert classify_width(1.0, (1.0, 1.0), configuration=config) is VisionPivotWidthState.INSUFFICIENT_DATA


def test_pivot_flight_plan_builds_provisional_bullish_context_and_action_zones():
    plan = build_pivot_flight_plan(plan_request())

    assert plan.instrument is RuntimeInstrument.NIFTY
    assert plan.trading_date == date(2026, 7, 29)
    assert plan.reference_session_date == date(2026, 7, 28)
    assert plan.cpr_relationship in {
        VisionPivotRelationship.HIGHER_VALUE,
        VisionPivotRelationship.OVERLAPPING_HIGHER_VALUE,
    }
    assert plan.camarilla_relationship in {
        VisionPivotRelationship.HIGHER_VALUE,
        VisionPivotRelationship.OVERLAPPING_HIGHER_VALUE,
    }
    assert plan.combined_context_state in {
        VisionPivotCombinedContext.BULLISH_ALIGNED,
        VisionPivotCombinedContext.MODERATELY_BULLISH,
    }
    assert plan.combined_directional_prior in {
        VisionPivotDirectionalPrior.BULLISH,
        VisionPivotDirectionalPrior.MODERATELY_BULLISH,
    }
    assert plan.opening_confirmation_required is True
    assert plan.scenario_status.value == "opening_confirmation_required"
    assert any(zone.label == "H3_IF_OPEN_ABOVE_H3" for zone in plan.preferred_bullish_action_zones)


def test_pivot_flight_plan_identifies_inside_narrow_breakout_potential():
    prior = daily(date(2026, 7, 27), 150.0, 70.0, 116.0)
    current = daily(date(2026, 7, 28), 112.0, 108.0, 110.0)
    sample = (
        daily(date(2026, 7, 21), 140.0, 80.0, 130.0),
        daily(date(2026, 7, 22), 140.0, 80.0, 130.0),
        daily(date(2026, 7, 23), 140.0, 80.0, 130.0),
        daily(date(2026, 7, 24), 140.0, 80.0, 130.0),
        daily(date(2026, 7, 25), 140.0, 80.0, 130.0),
        prior,
    )

    plan = build_pivot_flight_plan(plan_request(current_source=current, historical_daily_ohlc=sample))

    assert plan.cpr_relationship is VisionPivotRelationship.INSIDE_VALUE
    assert plan.camarilla_relationship is VisionPivotRelationship.INSIDE_VALUE
    assert plan.cpr_width_state is VisionPivotWidthState.NARROW
    assert plan.camarilla_width_state is VisionPivotWidthState.NARROW
    assert plan.combined_context_state is VisionPivotCombinedContext.BREAKOUT_POTENTIAL
    assert plan.expansion_tendency is VisionPivotTendency.HIGH


def test_pivot_flight_plan_reports_insufficient_data_without_history():
    plan = build_pivot_flight_plan(plan_request(historical_daily_ohlc=()))

    assert plan.cpr_relationship is VisionPivotRelationship.INSUFFICIENT_DATA
    assert plan.cpr_width_state is VisionPivotWidthState.INSUFFICIENT_DATA
    assert plan.camarilla_width_state is VisionPivotWidthState.INSUFFICIENT_DATA
    assert plan.combined_context_state is VisionPivotCombinedContext.INSUFFICIENT_DATA
    assert "Previous completed pivot reference is unavailable" in plan.warnings


def test_pivot_flight_plan_rejects_bad_timestamp_and_mutation():
    with pytest.raises(ValueError, match="generated_at must be timezone-aware"):
        plan_request(generated_at=datetime(2026, 7, 29, 8, 45))

    plan = build_pivot_flight_plan(plan_request())
    with pytest.raises(FrozenInstanceError):
        plan.opening_confirmation_required = False


def test_calculator_carries_pivot_context_without_promoting_candidate():
    plan = build_pivot_flight_plan(plan_request())
    item = snapshot(pivot_flight_plan=plan)
    report = validate_vision_method(item)

    assert item.pivot_flight_plan is plan
    assert item.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert report.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert any(reason == "Opening confirmation required" for reason in item.supporting_reasons)


def test_runtime_snapshot_exposes_pivot_flight_plan_without_requiring_trade_candidate():
    plan = build_pivot_flight_plan(plan_request())
    runtime = RuntimeSnapshot(
        RuntimeInstrument.NIFTY,
        "5m",
        RuntimeStatus.RUNNING,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        NOW,
        pivot_flight_plan=plan,
    )

    assert runtime.pivot_flight_plan is plan
    assert runtime.vision_trade_candidate is None


def test_forensic_trace_records_pivot_flight_plan(tmp_path):
    plan = build_pivot_flight_plan(plan_request())
    item = snapshot(pivot_flight_plan=plan)
    report = validate_vision_method(item)
    candidate = TradeCandidate(
        instrument=RuntimeInstrument.NIFTY,
        exchange=Exchange.NSE,
        timeframe=TimeFrame.FIVE_MINUTES,
        timestamp=NOW,
        candidate_state=TradeCandidateState.LONG,
        direction=TradeCandidateDirection.LONG,
        entry_zone="H3-H4",
        stop_loss_zone="Below Opening Range",
        target_zone="H4",
        confidence="high",
        reason="Vision Method long eligible",
        snapshot_reference=f"VisionMethodSnapshot:{NOW.isoformat()}",
        validation_reference=f"VisionMethodValidationReport:{NOW.isoformat()}",
    )
    trace = VisionForensicTrace(
        instrument=RuntimeInstrument.NIFTY,
        decision_timeframe=TimeFrame.FIVE_MINUTES,
        path=tmp_path / "trace.jsonl",
    )
    candle = Candle("NIFTY", "5m", NOW - timedelta(minutes=5), NOW, 100.0, 103.0, 99.0, 102.0, 1000)

    assert trace.record(
        snapshot=item,
        validation_report=report,
        source_candle=candle,
        runtime_timestamp=NOW,
        trade_candidate=candidate,
        risk_snapshot=None,
        paper_position=None,
        decision_audit=None,
        option_sync_status="SYNCHRONIZED",
        option_latency_ms=25.0,
    )
    payload = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")

    assert '"pivot_flight_plan"' in payload
    assert '"opening_confirmation_required":true' in payload
