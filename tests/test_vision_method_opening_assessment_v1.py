from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone

import pytest

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.event_bus import EventBus
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick
from engines.camarilla.calculator import CamarillaCalculator
from engines.cpr.calculator import CPRCalculator
from engines.runtime_adapter import adapt_vision_method_to_trade_candidate
from engines.vision_method import (
    VisionCandidateState,
    VisionCamarillaZone,
    VisionCPRRelation,
    VisionOpeningAcceptanceState,
    VisionOpeningActionZoneState,
    VisionOpeningCPRLocation,
    VisionOpeningCamarillaLocation,
    VisionOpeningGapState,
    VisionOpeningPivotValueLocation,
    VisionOpeningPriorRangeLocation,
    VisionOpeningScenario,
    VisionOpeningScenarioDirection,
    VisionOpeningScenarioStrength,
    VisionPivotCombinedContext,
    VisionPivotDirectionalPrior,
    VisionPivotFlightPlan,
    VisionPivotOpeningAssessmentRequest,
    VisionPivotRelationship,
    VisionPivotTendency,
    VisionPivotWidthState,
    VisionScenarioStatus,
    assess_pivot_opening,
    calculate_vision_method_snapshot,
    classify_open_vs_camarilla,
    classify_open_vs_cpr,
    classify_open_vs_prior_range,
    classify_opening_gap,
    classify_opening_value_location,
    validate_vision_method,
)
from tests.test_vision_method_calculator_v1 import IST, NOW, level, request


TRADING_DATE = date(2026, 7, 29)
REFERENCE_DATE = date(2026, 7, 28)
OPEN_TIME = datetime(2026, 7, 29, 9, 15, tzinfo=IST)


def prior_day() -> DailyOHLC:
    return DailyOHLC(REFERENCE_DATE, 100.0, 110.0, 90.0, 100.0)


def plan(
    *,
    combined_context: VisionPivotCombinedContext = VisionPivotCombinedContext.BULLISH_ALIGNED,
    prior: VisionPivotDirectionalPrior = VisionPivotDirectionalPrior.BULLISH,
    cpr_relationship: VisionPivotRelationship = VisionPivotRelationship.HIGHER_VALUE,
    camarilla_relationship: VisionPivotRelationship = VisionPivotRelationship.HIGHER_VALUE,
    scenario_status: VisionScenarioStatus = VisionScenarioStatus.OPENING_CONFIRMATION_REQUIRED,
    warnings: tuple[str, ...] = (),
) -> VisionPivotFlightPlan:
    return VisionPivotFlightPlan(
        instrument=RuntimeInstrument.NIFTY,
        trading_date=TRADING_DATE,
        reference_session_date=REFERENCE_DATE,
        generated_at=NOW,
        cpr_relationship=cpr_relationship,
        cpr_width_state=VisionPivotWidthState.NORMAL,
        cpr_width_value=2.0,
        cpr_directional_prior=prior,
        camarilla_relationship=camarilla_relationship,
        camarilla_width_state=VisionPivotWidthState.NORMAL,
        camarilla_width_value=8.0,
        camarilla_directional_prior=prior,
        combined_context_state=combined_context,
        combined_directional_prior=prior,
        expansion_tendency=VisionPivotTendency.MODERATE,
        balance_tendency=VisionPivotTendency.MODERATE,
        preferred_bullish_action_zones=(),
        preferred_bearish_action_zones=(),
        bullish_scenario="Bullish continuation remains provisional until opening confirms above value.",
        bearish_scenario="Bearish continuation remains provisional until opening confirms below value.",
        neutral_or_breakout_scenario="Inside value requires opening confirmation.",
        scenario_status=scenario_status,
        opening_confirmation_required=True,
        supporting_reasons=("Pivot context requires opening confirmation",),
        conflicting_reasons=(),
        warnings=warnings,
    )


def assessment(opening_price: float, flight_plan: VisionPivotFlightPlan | None = None):
    return assess_pivot_opening(
        VisionPivotOpeningAssessmentRequest(
            instrument=RuntimeInstrument.NIFTY,
            trading_date=TRADING_DATE,
            opening_price=opening_price,
            opening_timestamp=OPEN_TIME,
            flight_plan=flight_plan or plan(),
            level_context=level(),
        )
    )


def test_opening_classifiers_are_deterministic():
    ctx = level()

    assert classify_open_vs_prior_range(111.0, ctx) is VisionOpeningPriorRangeLocation.ABOVE_PRIOR_HIGH
    assert classify_open_vs_prior_range(100.0, ctx) is VisionOpeningPriorRangeLocation.INSIDE_PRIOR_RANGE
    assert classify_open_vs_prior_range(89.0, ctx) is VisionOpeningPriorRangeLocation.BELOW_PRIOR_LOW
    assert classify_open_vs_cpr(102.0, ctx) is VisionOpeningCPRLocation.ABOVE_CPR
    assert classify_open_vs_cpr(100.0, ctx) is VisionOpeningCPRLocation.INSIDE_CPR
    assert classify_open_vs_cpr(98.0, ctx) is VisionOpeningCPRLocation.BELOW_CPR
    assert classify_open_vs_camarilla(105.0, ctx) is VisionOpeningCamarillaLocation.ABOVE_H4
    assert classify_open_vs_camarilla(103.5, ctx) is VisionOpeningCamarillaLocation.BETWEEN_H3_H4
    assert classify_open_vs_camarilla(100.0, ctx) is VisionOpeningCamarillaLocation.BETWEEN_L3_H3
    assert classify_open_vs_camarilla(96.5, ctx) is VisionOpeningCamarillaLocation.BETWEEN_L4_L3
    assert classify_open_vs_camarilla(95.0, ctx) is VisionOpeningCamarillaLocation.BELOW_L4
    assert (
        classify_opening_value_location(
            VisionOpeningPriorRangeLocation.INSIDE_PRIOR_RANGE,
            VisionOpeningCPRLocation.INSIDE_CPR,
        )
        is VisionOpeningPivotValueLocation.IN_RANGE_IN_VALUE
    )
    assert classify_opening_gap(111.0, ctx) is VisionOpeningGapState.GAP_UP
    assert classify_opening_gap(89.0, ctx) is VisionOpeningGapState.GAP_DOWN
    assert classify_opening_gap(100.0, ctx) is VisionOpeningGapState.NO_MEANINGFUL_GAP


def test_bullish_pivot_context_accepts_supportive_open_and_activates_context_zone():
    result = assessment(105.0)

    assert result.opening_acceptance_state is VisionOpeningAcceptanceState.ACCEPTED
    assert result.active_scenario is VisionOpeningScenario.BULLISH_CONTINUATION
    assert result.scenario_direction is VisionOpeningScenarioDirection.BULLISH
    assert result.scenario_strength is VisionOpeningScenarioStrength.STRONG
    assert result.assessment_complete is True
    assert any(zone.zone_id.value == "h3_pullback_long_zone" for zone in result.activated_action_zones)
    assert all(zone.state is VisionOpeningActionZoneState.ACTIVE for zone in result.activated_action_zones)


def test_opposing_open_rejects_bullish_plan_without_creating_trade_candidate():
    result = assessment(95.0)
    snapshot = calculate_vision_method_snapshot(
        request(
            pivot_opening_assessment=result,
        )
    )
    report = validate_vision_method(snapshot)
    candidate = adapt_vision_method_to_trade_candidate(snapshot, report)

    assert result.opening_acceptance_state is VisionOpeningAcceptanceState.REJECTED
    assert result.active_scenario is VisionOpeningScenario.BEARISH_BREAKOUT_WATCH
    assert result.scenario_direction is VisionOpeningScenarioDirection.BEARISH
    assert snapshot.pivot_opening_assessment is result
    assert snapshot.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert candidate.direction.value == "long"
    assert not hasattr(result, "trade_candidate")


def test_bearish_pivot_context_accepts_supportive_open():
    result = assessment(
        95.0,
        plan(
            combined_context=VisionPivotCombinedContext.BEARISH_ALIGNED,
            prior=VisionPivotDirectionalPrior.BEARISH,
            cpr_relationship=VisionPivotRelationship.LOWER_VALUE,
            camarilla_relationship=VisionPivotRelationship.LOWER_VALUE,
        ),
    )

    assert result.opening_acceptance_state is VisionOpeningAcceptanceState.ACCEPTED
    assert result.active_scenario is VisionOpeningScenario.BEARISH_CONTINUATION
    assert result.scenario_direction is VisionOpeningScenarioDirection.BEARISH
    assert any(zone.zone_id.value == "l3_pullback_short_zone" for zone in result.activated_action_zones)


def test_inside_narrow_context_activates_breakout_watch_from_opening_location():
    flight_plan = plan(
        combined_context=VisionPivotCombinedContext.BREAKOUT_POTENTIAL,
        prior=VisionPivotDirectionalPrior.BREAKOUT_UNRESOLVED,
        cpr_relationship=VisionPivotRelationship.INSIDE_VALUE,
        camarilla_relationship=VisionPivotRelationship.INSIDE_VALUE,
    )

    result = assessment(105.0, flight_plan)

    assert result.opening_acceptance_state is VisionOpeningAcceptanceState.PARTIALLY_ACCEPTED
    assert result.active_scenario is VisionOpeningScenario.BULLISH_BREAKOUT_WATCH
    assert any(zone.zone_id.value == "h4_bullish_breakout_watch_zone" for zone in result.activated_action_zones)


def test_conflicted_plan_stays_unresolved_when_opening_does_not_resolve_direction():
    result = assessment(
        100.0,
        plan(
            combined_context=VisionPivotCombinedContext.CONFLICTED,
            prior=VisionPivotDirectionalPrior.CONFLICTED,
            cpr_relationship=VisionPivotRelationship.HIGHER_VALUE,
            camarilla_relationship=VisionPivotRelationship.LOWER_VALUE,
        ),
    )

    assert result.opening_acceptance_state is VisionOpeningAcceptanceState.UNRESOLVED
    assert result.active_scenario is VisionOpeningScenario.CONFLICTED
    assert result.scenario_direction is VisionOpeningScenarioDirection.CONFLICTED
    assert result.assessment_complete is False


def test_opening_assessment_rejects_invalid_contract_and_is_immutable():
    with pytest.raises(ValueError, match="opening_timestamp must be timezone-aware"):
        assess_pivot_opening(
            VisionPivotOpeningAssessmentRequest(
                instrument=RuntimeInstrument.NIFTY,
                trading_date=TRADING_DATE,
                opening_price=100.0,
                opening_timestamp=datetime(2026, 7, 29, 9, 15),
                flight_plan=plan(),
                level_context=level(),
            )
        )

    result = assessment(105.0)
    with pytest.raises(FrozenInstanceError):
        result.opening_price = 100.0


def test_runtime_captures_first_active_session_open_once():
    runtime = _runtime_with_daily_context()

    runtime.process_tick(_tick(datetime(2026, 7, 29, 9, 15, tzinfo=IST), 105.0))
    runtime.process_tick(_tick(datetime(2026, 7, 29, 9, 16, tzinfo=IST), 99.0))
    snapshot = runtime.snapshot()

    assert snapshot.pivot_opening_assessment is not None
    assert snapshot.pivot_opening_assessment.opening_price == 105.0
    assert snapshot.pivot_opening_assessment.opening_timestamp == datetime(2026, 7, 29, 9, 15, tzinfo=IST)


def test_runtime_ignores_pre_open_tick_and_restores_open_from_same_session_history():
    runtime = _runtime_with_daily_context()
    runtime.process_tick(_tick(datetime(2026, 7, 29, 9, 10, tzinfo=IST), 200.0))
    runtime.process_tick(_tick(datetime(2026, 7, 29, 9, 15, tzinfo=IST), 105.0))

    assert runtime.snapshot().pivot_opening_assessment.opening_price == 105.0

    restarted = _runtime_with_daily_context()
    restarted.warm_up_candles((_candle(datetime(2026, 7, 29, 9, 15, tzinfo=IST), 107.0),))
    restored = restarted.snapshot().pivot_opening_assessment

    assert restored is not None
    assert restored.opening_price == 107.0
    assert restored.opening_timestamp == datetime(2026, 7, 29, 9, 15, tzinfo=IST)


def _runtime_with_daily_context() -> SymbolRuntime:
    runtime = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m", "15m")),
        RuntimeInstrument.NIFTY,
    )
    runtime.start()
    runtime.process_daily_ohlc(prior_day(), levels_trading_date=TRADING_DATE)
    return runtime


def _tick(timestamp: datetime, price: float) -> Tick:
    return Tick(Instrument.NIFTY, Exchange.NSE, timestamp, price, 100, price - 0.5, price + 0.5, 0)


def _candle(start: datetime, open_: float) -> Candle:
    return Candle("NIFTY", "1m", start, start + timedelta(minutes=1), open_, open_ + 1.0, open_ - 1.0, open_ + 0.5, 1000)
