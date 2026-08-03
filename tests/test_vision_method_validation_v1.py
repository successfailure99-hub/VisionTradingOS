from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from engines.vision_method import (
    VisionADRContext,
    VisionBOS,
    VisionBreakerBlock,
    VisionBreakerBlockState,
    VisionBreakDirection,
    VisionBreakStrength,
    VisionCHoCH,
    VisionCPRContext,
    VisionCPRRelation,
    VisionCamarillaContext,
    VisionCamarillaZone,
    VisionCandidateState,
    VisionLevelContext,
    VisionLevelQuality,
    VisionLiquidityContext,
    VisionLiquidityLevel,
    VisionLiquidityPool,
    VisionLiquiditySweep,
    VisionMethodCalculationRequest,
    VisionMethodValidationResult,
    VisionMitigationState,
    VisionMSS,
    VisionOpeningRangeContext,
    VisionOpeningRangeState,
    VisionOptionConfirmation,
    VisionOptionConfirmationContext,
    VisionPreviousDayContext,
    VisionPreviousDayRelation,
    VisionRangeLocation,
    VisionReversalState,
    VisionSetupQualificationContext,
    VisionSetupQuality,
    VisionSetupType,
    VisionStructureContext,
    VisionStructureEventContext,
    VisionStructureEventPhase,
    VisionStructurePattern,
    VisionStructureTrend,
    VisionSweepDirection,
    VisionSwingPoint,
    VisionSwingType,
    VisionVWAPContext,
    VisionVWAPRelation,
    calculate_vision_method_snapshot,
    validate_vision_method,
    validate_vision_method_validation_report,
)


IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 7, 29, 10, 30, tzinfo=IST)
OPEN_START = datetime(2026, 7, 29, 9, 15, tzinfo=IST)
OPEN_END = datetime(2026, 7, 29, 9, 30, tzinfo=IST)


def previous_day() -> VisionPreviousDayContext:
    return VisionPreviousDayContext(
        previous_high=110.0,
        previous_low=90.0,
        previous_close=100.0,
        virgin_cpr=False,
        distance_previous_high=-5.0,
        distance_previous_low=15.0,
        previous_day_relation=VisionPreviousDayRelation.INSIDE_PREVIOUS_RANGE,
    )


def level(
    *,
    cpr: VisionCPRRelation = VisionCPRRelation.ABOVE_CPR,
    zone: VisionCamarillaZone = VisionCamarillaZone.H3_H4,
    vwap: VisionVWAPRelation = VisionVWAPRelation.ABOVE_VWAP,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
    include_adr: bool = True,
    include_vwap: bool = True,
) -> VisionLevelContext:
    return VisionLevelContext(
        cpr_context=VisionCPRContext(cpr, 99.0, 101.0, 100.0, 2.0, 2.0),
        camarilla_context=VisionCamarillaContext(zone, 103.0, 104.0, 105.0, 106.0, 97.0, 96.0, 95.0, 94.0),
        previous_day_context=previous_day(),
        adr_context=VisionADRContext(32.0, 68.0, False, False, "normal", "normal") if include_adr else None,
        vwap_context=VisionVWAPContext(vwap, 100.0, 1.0, 1.0) if include_vwap else None,
        quality=quality,
        missing_evidence=("ADR",) if not include_adr else (),
    )


def opening(
    *,
    complete: bool = True,
    state: VisionOpeningRangeState = VisionOpeningRangeState.BREAK_ABOVE,
    direction: VisionBreakDirection = VisionBreakDirection.UP,
    location: VisionRangeLocation = VisionRangeLocation.ABOVE_RANGE,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionOpeningRangeContext:
    return VisionOpeningRangeContext(
        opening_start_time=OPEN_START,
        opening_end_time=OPEN_END,
        opening_high=102.0,
        opening_low=99.0,
        opening_width=3.0,
        range_complete=complete,
        current_location=location,
        break_direction=direction,
        retest_state=state,
        false_break=state is VisionOpeningRangeState.FALSE_BREAK,
        elapsed_minutes=15 if complete else 10,
        quality=quality,
    )


def swing(price: float, index: int, type_: VisionSwingType) -> VisionSwingPoint:
    return VisionSwingPoint(price, OPEN_START + timedelta(minutes=5 * index), index, 4, type_)


def structure(
    *,
    trend: VisionStructureTrend = VisionStructureTrend.BULLISH,
    pattern: VisionStructurePattern = VisionStructurePattern.HH,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionStructureContext:
    return VisionStructureContext(
        current_swing_high=swing(110.0, 5, VisionSwingType.HIGH),
        current_swing_low=swing(100.0, 6, VisionSwingType.LOW),
        previous_swing_high=swing(105.0, 1, VisionSwingType.HIGH),
        previous_swing_low=swing(95.0, 2, VisionSwingType.LOW),
        trend=trend,
        structure_state=pattern,
        last_confirmed_swing=swing(110.0, 5, VisionSwingType.HIGH),
        quality=quality,
    )


def liquidity(
    *,
    sweep: VisionLiquiditySweep = VisionLiquiditySweep.NONE,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionLiquidityContext:
    equal_highs = ()
    pool = VisionLiquidityPool.NONE
    direction = VisionSweepDirection.NONE
    if sweep is VisionLiquiditySweep.BUY_SIDE_SWEEP:
        equal_highs = (VisionLiquidityLevel(110.0, OPEN_START, OPEN_START + timedelta(minutes=5), (0, 1), VisionSwingType.HIGH, 0.0005),)
        pool = VisionLiquidityPool.BUY_SIDE
        direction = VisionSweepDirection.BUY_SIDE
    return VisionLiquidityContext(
        equal_highs=equal_highs,
        equal_lows=(),
        liquidity_pool=pool,
        liquidity_sweep=sweep,
        sweep_direction=direction,
        fair_value_gap=None,
        order_block=None,
        breaker_block=VisionBreakerBlock(VisionBreakerBlockState.NOT_EVALUATED),
        mitigation=VisionMitigationState.NOT_EVALUATED,
        quality=quality,
    )


def structure_event(
    *,
    bos: VisionBOS = VisionBOS.BULLISH_BOS,
    choch: VisionCHoCH = VisionCHoCH.NONE,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionStructureEventContext:
    if choch is not VisionCHoCH.NONE:
        return VisionStructureEventContext(
            bos=VisionBOS.NONE,
            choch=choch,
            mss=VisionMSS.MARKET_STRUCTURE_SHIFT,
            continuation=VisionStructureEventPhase.REVERSAL,
            reversal=VisionReversalState.BULLISH_REVERSAL if choch is VisionCHoCH.BULLISH_CHOCH else VisionReversalState.BEARISH_REVERSAL,
            break_strength=VisionBreakStrength.STRONG,
            quality=quality,
        )
    return VisionStructureEventContext(
        bos=bos,
        choch=VisionCHoCH.NONE,
        mss=VisionMSS.NONE,
        continuation=VisionStructureEventPhase.CONTINUATION if bos is not VisionBOS.NONE else VisionStructureEventPhase.NONE,
        reversal=VisionReversalState.NONE,
        break_strength=VisionBreakStrength.STRONG if bos is not VisionBOS.NONE else VisionBreakStrength.NONE,
        quality=quality,
    )


def setup(
    *,
    setup_type: VisionSetupType = VisionSetupType.TREND_CONTINUATION,
    quality: VisionSetupQuality = VisionSetupQuality.HIGH,
    supporting: tuple[str, ...] = ("Above CPR", "Above H3", "Bullish BOS"),
    blocking: tuple[str, ...] = (),
    eligible: bool = True,
) -> VisionSetupQualificationContext:
    return VisionSetupQualificationContext(
        setup_type=setup_type,
        setup_quality=quality,
        blocking_reasons=blocking,
        supporting_reasons=supporting,
        eligible_for_option_confirmation=eligible,
    )


def option(
    *,
    state: VisionOptionConfirmation = VisionOptionConfirmation.CONFIRMS,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
    supporting: tuple[str, ...] = ("Put writing supports setup",),
    contradicting: tuple[str, ...] = (),
    neutral: tuple[str, ...] = (),
) -> VisionOptionConfirmationContext:
    if state is VisionOptionConfirmation.CONTRADICTS and not contradicting:
        contradicting = ("Call writing contradicts setup",)
        supporting = ()
    if state is VisionOptionConfirmation.UNAVAILABLE:
        quality = VisionLevelQuality.INSUFFICIENT
        supporting = ()
        neutral = ("Option chain unavailable",)
    return VisionOptionConfirmationContext(
        confirmation_state=state,
        supporting_factors=supporting,
        contradicting_factors=contradicting,
        neutral_factors=neutral,
        quality=quality,
        timestamp=NOW,
    )


def snapshot(**overrides):
    values = {
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": TimeFrame.FIVE_MINUTES,
        "timestamp": NOW,
        "level_context": level(),
        "opening_range_context": opening(),
        "structure_context": structure(),
        "liquidity_context": liquidity(),
        "structure_event_context": structure_event(),
        "setup_qualification_context": setup(),
        "option_confirmation_context": option(),
    }
    values.update(overrides)
    return calculate_vision_method_snapshot(VisionMethodCalculationRequest(**values))


def test_valid_bullish_snapshot_produces_ordered_validation_trace():
    report = validate_vision_method(snapshot())

    assert report.validation_result is VisionMethodValidationResult.VALID
    assert report.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert report.metrics.completed_steps == 10
    assert report.metrics.failed_steps == 0
    assert report.metrics.missing_steps == 0
    assert tuple(step.stage for step in report.trace[:3]) == ("CPR", "Camarilla", "Previous Day")
    assert report.trace[-1].stage == "FINAL"
    assert report.trace[-1].observed == "long_eligible"


def test_valid_bearish_snapshot_records_short_eligible_methodology():
    report = validate_vision_method(
        snapshot(
            level_context=level(
                cpr=VisionCPRRelation.BELOW_CPR,
                zone=VisionCamarillaZone.L3_L4,
                vwap=VisionVWAPRelation.BELOW_VWAP,
            ),
            opening_range_context=opening(
                state=VisionOpeningRangeState.BREAK_BELOW,
                direction=VisionBreakDirection.DOWN,
                location=VisionRangeLocation.BELOW_RANGE,
            ),
            structure_context=structure(trend=VisionStructureTrend.BEARISH, pattern=VisionStructurePattern.LL),
            structure_event_context=structure_event(bos=VisionBOS.BEARISH_BOS),
            setup_qualification_context=setup(supporting=("Below CPR", "Below L3", "Bearish BOS")),
        )
    )

    assert report.validation_result is VisionMethodValidationResult.VALID
    assert report.candidate_state is VisionCandidateState.SHORT_ELIGIBLE
    assert "below_cpr" in report.level_context


def test_option_chain_contradiction_reduces_quality_without_blocking():
    report = validate_vision_method(snapshot(option_confirmation_context=option(state=VisionOptionConfirmation.CONTRADICTS)))

    assert report.validation_result is VisionMethodValidationResult.PARTIAL
    assert report.candidate_state is VisionCandidateState.PREPARE_LONG
    assert report.metrics.blocking_stage is None
    assert report.metrics.failed_steps == 0
    assert report.trace[9].status == "pass"
    assert report.blocking_reasons == ()
    assert "Call writing contradicts setup" in report.trace[9].detail


def test_insufficient_data_report_exposes_missing_methodology_state():
    report = validate_vision_method(
        snapshot(
            level_context=level(quality=VisionLevelQuality.INSUFFICIENT),
            option_confirmation_context=option(state=VisionOptionConfirmation.UNAVAILABLE),
        )
    )

    assert report.validation_result is VisionMethodValidationResult.INSUFFICIENT_DATA
    assert report.candidate_state is VisionCandidateState.INSUFFICIENT_DATA
    assert report.metrics.missing_steps >= 1
    assert report.metrics.blocking_stage == "CPR"


def test_missing_optional_context_creates_partial_report_with_exact_stage():
    report = validate_vision_method(snapshot(level_context=level(quality=VisionLevelQuality.PARTIAL, include_adr=False)))

    assert report.validation_result is VisionMethodValidationResult.PARTIAL
    assert report.metrics.blocking_stage is None
    assert report.trace[3].stage == "ADR"
    assert report.trace[3].status == "missing"


def test_missing_option_confirmation_continues_as_partial_methodology():
    report = validate_vision_method(snapshot(option_confirmation_context=option(state=VisionOptionConfirmation.UNAVAILABLE)))

    assert report.validation_result is VisionMethodValidationResult.PARTIAL
    assert report.candidate_state is VisionCandidateState.PREPARE_LONG
    assert report.metrics.blocking_stage is None
    assert report.trace[9].stage == "Option Chain"
    assert report.trace[9].status == "missing"
    assert report.blocking_reasons == ()


def test_opening_range_blocking_stage_is_visible():
    report = validate_vision_method(
        snapshot(
            opening_range_context=opening(
                complete=False,
                state=VisionOpeningRangeState.WAITING,
                direction=VisionBreakDirection.NONE,
                location=VisionRangeLocation.INSIDE_RANGE,
            )
        )
    )

    assert report.validation_result is VisionMethodValidationResult.PARTIAL
    assert report.candidate_state is VisionCandidateState.WAIT
    assert report.metrics.blocking_stage == "Opening Range"


def test_export_record_is_deterministic_and_serializable():
    report = validate_vision_method(snapshot())
    payload = asdict(report.export_record)

    assert payload["instrument"] == "NIFTY"
    assert payload["timeframe"] == "5m"
    assert payload["validation_result"] == "valid"
    assert payload["trace"][0] == "STEP 1 | CPR | above_cpr | pass"
    assert json.loads(json.dumps(payload))["candidate_state"] == "long_eligible"


def test_validation_report_is_immutable():
    report = validate_vision_method(snapshot())

    with pytest.raises(FrozenInstanceError):
        report.quality = "low"
    with pytest.raises(FrozenInstanceError):
        report.metrics.completed_steps = 0


def test_validator_rejects_invalid_inputs_and_export_mismatches():
    with pytest.raises(TypeError):
        validate_vision_method(None)

    report = validate_vision_method(snapshot())
    bad_export = replace(report.export_record, instrument="BANKNIFTY")
    with pytest.raises(ValueError, match="export instrument mismatch"):
        validate_vision_method_validation_report(replace(report, export_record=bad_export))
