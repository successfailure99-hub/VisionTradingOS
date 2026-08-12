from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from engines.vision_method import (
    VisionBOS,
    VisionBreakStrength,
    VisionCandlestickPattern,
    VisionCHoCH,
    VisionLevelQuality,
    VisionLiquidityPool,
    VisionLiquiditySweep,
    VisionMSS,
    VisionPivotConfluenceContext,
    VisionPivotHotZone,
    VisionPivotReferenceFamily,
    VisionPivotReferenceKind,
    VisionPivotZoneAlignment,
    VisionPivotZoneDirectionalRole,
    VisionPivotZoneMember,
    VisionPivotZoneQuality,
    VisionPivotZoneStatus,
    VisionPivotZoneStrength,
    VisionPivotZoneType,
    VisionPriceActionTriggerStageStatus,
    VisionPriceActionTriggerConfiguration,
    VisionPriceActionTriggerRequest,
    VisionReversalState,
    VisionStructureEventContext,
    VisionStructureEventPhase,
    VisionSweepDirection,
    VisionTriggerAcceptanceState,
    VisionTriggerBreakState,
    VisionTriggerInteractionState,
    VisionTriggerQuality,
    VisionTriggerRetestState,
    VisionTriggerType,
    VisionTriggerZoneEvent,
    build_price_action_trigger_context,
    failed_price_action_trigger_stage_result,
    price_action_trigger_stage_result_from_context,
)


IST = ZoneInfo("Asia/Kolkata")
TRADING_DATE = date(2026, 7, 29)
START = datetime(2026, 7, 29, 9, 15, tzinfo=IST)


def candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    start = START + timedelta(minutes=5 * index)
    return Candle("NIFTY", "5m", start, start + timedelta(minutes=5), open_, high, low, close, 1000)


def zone(
    role: VisionPivotZoneDirectionalRole,
    zone_type: VisionPivotZoneType,
    *,
    low: float = 100.0,
    high: float = 100.2,
    quality: VisionPivotZoneQuality = VisionPivotZoneQuality.HIGH,
    kind: VisionPivotReferenceKind = VisionPivotReferenceKind.CAMARILLA_H3,
) -> VisionPivotHotZone:
    member = VisionPivotZoneMember(
        family=VisionPivotReferenceFamily.CAMARILLA,
        kind=kind,
        label=kind.value,
        price=(low + high) / 2,
        role_hint=role,
    )
    cpr = VisionPivotZoneMember(
        family=VisionPivotReferenceFamily.CPR,
        kind=VisionPivotReferenceKind.CPR_PIVOT,
        label="CPR Pivot",
        price=(low + high) / 2,
        role_hint=role,
    )
    return VisionPivotHotZone(
        instrument=RuntimeInstrument.NIFTY,
        trading_date=TRADING_DATE,
        zone_low=low,
        zone_high=high,
        zone_center=(low + high) / 2,
        member_references=(member, cpr),
        reference_families=(VisionPivotReferenceFamily.CAMARILLA, VisionPivotReferenceFamily.CPR),
        independent_family_count=2,
        zone_type=zone_type,
        directional_role=role,
        quality=quality,
        strength=VisionPivotZoneStrength.STRONG,
        active_scenario_alignment=VisionPivotZoneAlignment.ALIGNED,
        opening_assessment_alignment=VisionPivotZoneAlignment.ALIGNED,
        status=VisionPivotZoneStatus.ACTIVE,
        supporting_reasons=("Hot zone",),
        conflicting_reasons=(),
        warnings=(),
        current_price_relation=__import__("engines.vision_method", fromlist=["VisionPivotPriceRelation"]).VisionPivotPriceRelation.INSIDE,
        created_at=START + timedelta(minutes=30),
    )


def confluence(item: VisionPivotHotZone, timestamp: datetime) -> VisionPivotConfluenceContext:
    return VisionPivotConfluenceContext(
        instrument=RuntimeInstrument.NIFTY,
        timeframe=TimeFrame.FIVE_MINUTES,
        trading_date=TRADING_DATE,
        timestamp=timestamp,
        hot_zones=(item,),
        top_bullish_interest_zones=(item,) if item.directional_role is VisionPivotZoneDirectionalRole.BULLISH_SUPPORT else (),
        top_bearish_interest_zones=(item,) if item.directional_role is VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE else (),
        top_breakout_decision_zones=(item,) if item.zone_type is VisionPivotZoneType.BREAKOUT_DECISION_ZONE else (),
        top_neutral_or_target_zones=(),
        quality=VisionLevelQuality.FULL,
        status=VisionPivotZoneStatus.ACTIVE,
        warnings=(),
    )


def structure_event(bullish: bool = True) -> VisionStructureEventContext:
    return VisionStructureEventContext(
        bos=VisionBOS.BULLISH_BOS if bullish else VisionBOS.BEARISH_BOS,
        choch=VisionCHoCH.NONE,
        mss=VisionMSS.NONE,
        continuation=VisionStructureEventPhase.CONTINUATION,
        reversal=VisionReversalState.NONE,
        break_strength=VisionBreakStrength.NORMAL,
        quality=VisionLevelQuality.FULL,
    )


def request(
    candles: tuple[Candle, ...],
    hot_zone: VisionPivotHotZone,
    *,
    previous_context=None,
    event: VisionStructureEventContext | None = None,
) -> VisionPriceActionTriggerRequest:
    timestamp = candles[-1].end_time
    return VisionPriceActionTriggerRequest(
        instrument=RuntimeInstrument.NIFTY,
        timeframe=TimeFrame.FIVE_MINUTES,
        trading_date=TRADING_DATE,
        timestamp=timestamp,
        candles=candles,
        pivot_confluence_context=confluence(hot_zone, timestamp),
        structure_event_context=event,
        previous_context=previous_context,
    )


def build(candles: tuple[Candle, ...], hot_zone: VisionPivotHotZone, **kwargs):
    return build_price_action_trigger_context(request(candles, hot_zone, **kwargs))


def test_stage_result_classifies_no_trigger_without_technical_failure():
    item = zone(VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE, VisionPivotZoneType.RESISTANCE_HOT_ZONE)
    context = build((candle(0, 99.8, 100.1, 99.7, 100.0),), item)

    result = price_action_trigger_stage_result_from_context(context, snapshot_generation="NIFTY:5m:2026-07-29T09:20:00+05:30")

    assert result.status in {
        VisionPriceActionTriggerStageStatus.EVALUATED_NO_TRIGGER,
        VisionPriceActionTriggerStageStatus.EVALUATED_INDECISION,
    }
    assert result.trigger_context is context
    assert result.failure_type is None
    assert result.failure_reason is None
    assert result.source_candle_reference.startswith("candle:NIFTY:5m:")


def test_stage_result_preserves_typeerror_failure_details():
    exc = TypeError("candles must contain Candle objects.")
    result = failed_price_action_trigger_stage_result(
        exc=exc,
        decision_timestamp=START + timedelta(minutes=5),
        source_candle_reference="candle:NIFTY:5m:bad",
        trigger_zone_reference="hot_zone:bad",
        snapshot_generation="NIFTY:5m:2026-07-29T09:20:00+05:30",
    )

    assert result.status is VisionPriceActionTriggerStageStatus.TRIGGER_ASSEMBLY_FAILED
    assert result.trigger_context is None
    assert result.failure_type == "TypeError"
    assert result.failure_reason == "candles must contain Candle objects."
    assert result.source_candle_reference == "candle:NIFTY:5m:bad"


def test_stage_result_preserves_valueerror_failure_details():
    exc = ValueError("candle timeframe mismatch.")
    result = failed_price_action_trigger_stage_result(
        exc=exc,
        decision_timestamp=START + timedelta(minutes=5),
        source_candle_reference="candle:NIFTY:1m:bad",
        trigger_zone_reference="hot_zone:bad",
        snapshot_generation="NIFTY:5m:2026-07-29T09:20:00+05:30",
    )

    assert result.status is VisionPriceActionTriggerStageStatus.TRIGGER_ASSEMBLY_FAILED
    assert result.failure_type == "ValueError"
    assert result.failure_reason == "candle timeframe mismatch."


def test_first_touch_and_penetration_are_not_rejection_or_breakout():
    item = zone(VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE, VisionPivotZoneType.RESISTANCE_HOT_ZONE)
    context = build((candle(0, 99.8, 100.1, 99.7, 100.0),), item)
    assert context.trigger.interaction_state in {
        VisionTriggerInteractionState.TESTING,
        VisionTriggerInteractionState.PENETRATING,
    }
    assert context.trigger.trigger_type is VisionTriggerType.NO_TRIGGER
    assert context.trigger.acceptance_state is VisionTriggerAcceptanceState.NONE


def test_h3_bearish_rejection_is_responsive_not_automatic_short_entry():
    item = zone(VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE, VisionPivotZoneType.RESISTANCE_HOT_ZONE)
    context = build((candle(0, 100.15, 100.9, 99.7, 99.8),), item)
    assert context.trigger.trigger_type is VisionTriggerType.BEARISH_REJECTION
    assert context.trigger.trigger_quality in {VisionTriggerQuality.LOW, VisionTriggerQuality.MEDIUM, VisionTriggerQuality.HIGH}
    assert "trade" not in " ".join(context.trigger.supporting_reasons).casefold()


def test_l3_bullish_rejection_is_responsive():
    item = zone(
        VisionPivotZoneDirectionalRole.BULLISH_SUPPORT,
        VisionPivotZoneType.SUPPORT_HOT_ZONE,
        kind=VisionPivotReferenceKind.CAMARILLA_L3,
    )
    context = build((candle(0, 100.05, 100.4, 99.2, 100.35),), item)
    assert context.trigger.trigger_type is VisionTriggerType.BULLISH_REJECTION
    assert context.trigger.candlestick_pattern is VisionCandlestickPattern.BULLISH_WICK_REVERSAL


def test_h4_break_acceptance_and_failed_breakout_are_distinct():
    item = zone(
        VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE,
        VisionPivotZoneType.BREAKOUT_DECISION_ZONE,
        kind=VisionPivotReferenceKind.CAMARILLA_H4,
    )
    accepted = build((candle(0, 99.8, 101.0, 99.7, 100.9),), item)
    assert accepted.trigger.trigger_type is VisionTriggerType.BULLISH_INITIATIVE_BREAKOUT
    assert accepted.trigger.acceptance_state is VisionTriggerAcceptanceState.ACCEPTED_UP

    failed = build((candle(0, 100.1, 100.9, 99.6, 99.8),), item)
    assert failed.trigger.trigger_type is VisionTriggerType.BEARISH_FAILED_BREAKOUT
    assert failed.trigger.acceptance_state is VisionTriggerAcceptanceState.FAILED_UP


def test_l4_breakdown_acceptance_and_failed_breakdown_are_distinct():
    item = zone(
        VisionPivotZoneDirectionalRole.BREAKDOWN_DOWNSIDE,
        VisionPivotZoneType.BREAKOUT_DECISION_ZONE,
        kind=VisionPivotReferenceKind.CAMARILLA_L4,
    )
    accepted = build((candle(0, 100.4, 100.5, 99.0, 99.2),), item)
    assert accepted.trigger.trigger_type is VisionTriggerType.BEARISH_INITIATIVE_BREAKOUT
    assert accepted.trigger.acceptance_state is VisionTriggerAcceptanceState.ACCEPTED_DOWN

    failed = build((candle(0, 100.0, 100.5, 99.1, 100.4),), item)
    assert failed.trigger.trigger_type is VisionTriggerType.BULLISH_FAILED_BREAKOUT
    assert failed.trigger.acceptance_state is VisionTriggerAcceptanceState.FAILED_DOWN


def test_retest_requires_prior_acceptance_and_then_hold_or_failure():
    item = zone(
        VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE,
        VisionPivotZoneType.BREAKOUT_DECISION_ZONE,
        kind=VisionPivotReferenceKind.CAMARILLA_H4,
    )
    first_touch = build((candle(0, 99.8, 100.1, 99.7, 100.0),), item)
    assert first_touch.trigger.retest_state is VisionTriggerRetestState.NONE

    accepted = build((candle(0, 99.8, 101.0, 99.7, 100.9),), item)
    hold = build(
        (candle(0, 99.8, 101.0, 99.7, 100.9), candle(1, 100.8, 101.1, 100.1, 100.6)),
        item,
        previous_context=accepted,
    )
    assert hold.trigger.trigger_type is VisionTriggerType.BULLISH_RETEST_HOLD
    assert hold.trigger.retest_state is VisionTriggerRetestState.RETEST_HOLD

    failure = build(
        (candle(0, 99.8, 101.0, 99.7, 100.9), candle(1, 100.6, 100.7, 99.5, 99.7)),
        item,
        previous_context=accepted,
    )
    assert failure.trigger.trigger_type is VisionTriggerType.BEARISH_FAILED_BREAKOUT
    assert failure.trigger.retest_state is VisionTriggerRetestState.RETEST_FAILURE


def test_wick_outside_extreme_and_doji_patterns_are_location_aware():
    support = zone(
        VisionPivotZoneDirectionalRole.BULLISH_SUPPORT,
        VisionPivotZoneType.SUPPORT_HOT_ZONE,
        kind=VisionPivotReferenceKind.CAMARILLA_L3,
    )
    wick = build((candle(0, 100.05, 100.4, 99.2, 100.35),), support)
    assert wick.trigger.candlestick_pattern is VisionCandlestickPattern.BULLISH_WICK_REVERSAL

    outside = build((candle(0, 100.2, 100.3, 99.8, 100.0), candle(1, 100.0, 100.45, 99.7, 100.4)), support)
    assert outside.trigger.candlestick_pattern is VisionCandlestickPattern.BULLISH_OUTSIDE_REVERSAL

    doji = build((candle(0, 100.0, 100.2, 99.95, 100.01),), support)
    assert doji.trigger.trigger_type is VisionTriggerType.INDECISION

    resistance = zone(VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE, VisionPivotZoneType.RESISTANCE_HOT_ZONE)
    extreme = build(
        (
            candle(0, 100.0, 100.2, 99.9, 100.1),
            candle(1, 100.1, 100.2, 99.9, 100.0),
            candle(2, 100.0, 100.1, 99.9, 100.0),
            candle(3, 100.0, 100.1, 99.9, 100.0),
            candle(4, 100.0, 100.2, 99.9, 100.1),
            candle(5, 100.1, 102.0, 99.8, 101.8),
            candle(6, 101.8, 101.9, 99.6, 99.7),
        ),
        resistance,
    )
    assert extreme.trigger.candlestick_pattern is VisionCandlestickPattern.BEARISH_EXTREME_REVERSAL


def test_structure_alignment_can_improve_breakout_evidence_without_recalculating_structure():
    item = zone(
        VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE,
        VisionPivotZoneType.BREAKOUT_DECISION_ZONE,
        kind=VisionPivotReferenceKind.CAMARILLA_H4,
    )
    context = build((candle(0, 99.8, 101.0, 99.7, 100.9),), item, event=structure_event(True))
    assert context.trigger.structure_alignment.value in {"aligned", "supporting"}
    assert context.trigger.trigger_quality in {VisionTriggerQuality.MEDIUM, VisionTriggerQuality.HIGH}


def test_bounded_memory_rejects_invalid_transition_order_and_suppresses_duplicates():
    item = zone(
        VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE,
        VisionPivotZoneType.BREAKOUT_DECISION_ZONE,
        kind=VisionPivotReferenceKind.CAMARILLA_H4,
    )
    config = VisionPriceActionTriggerConfiguration(max_zone_event_history=2)
    request_one = request((candle(0, 99.8, 101.0, 99.7, 100.9),), item)
    accepted = build_price_action_trigger_context(request_one)
    duplicate = build_price_action_trigger_context(
        VisionPriceActionTriggerRequest(
            instrument=RuntimeInstrument.NIFTY,
            timeframe=TimeFrame.FIVE_MINUTES,
            trading_date=TRADING_DATE,
            timestamp=candle(0, 99.8, 101.0, 99.7, 100.9).end_time,
            candles=(candle(0, 99.8, 101.0, 99.7, 100.9),),
            pivot_confluence_context=confluence(item, candle(0, 99.8, 101.0, 99.7, 100.9).end_time),
            previous_context=accepted,
            configuration=config,
        )
    )
    assert len(duplicate.event_history) == 1
    assert duplicate.event_history[-1].acceptance_state is VisionTriggerAcceptanceState.ACCEPTED_UP

    second = build_price_action_trigger_context(
        VisionPriceActionTriggerRequest(
            instrument=RuntimeInstrument.NIFTY,
            timeframe=TimeFrame.FIVE_MINUTES,
            trading_date=TRADING_DATE,
            timestamp=candle(1, 100.8, 101.1, 100.1, 100.6).end_time,
            candles=(candle(0, 99.8, 101.0, 99.7, 100.9), candle(1, 100.8, 101.1, 100.1, 100.6)),
            pivot_confluence_context=confluence(item, candle(1, 100.8, 101.1, 100.1, 100.6).end_time),
            previous_context=duplicate,
            configuration=config,
        )
    )
    assert len(second.event_history) <= 2

    bad_event = VisionTriggerZoneEvent(
        zone_reference=second.event_history[-1].zone_reference,
        timestamp=START,
        interaction_state=VisionTriggerInteractionState.ACCEPTED,
        break_state=VisionTriggerBreakState.BROKEN_UP,
        acceptance_state=VisionTriggerAcceptanceState.ACCEPTED_UP,
        retest_state=VisionTriggerRetestState.NONE,
        trigger_type=VisionTriggerType.BULLISH_INITIATIVE_BREAKOUT,
        source_candle_reference="bad",
    )
    with pytest.raises(ValueError, match="event_history must be ordered"):
        type(second)(
            instrument=second.instrument,
            trading_date=second.trading_date,
            timeframe=second.timeframe,
            timestamp=second.timestamp,
            trigger=second.trigger,
            event_history=(second.event_history[-1], bad_event),
            quality=second.quality,
            status=second.status,
            warnings=second.warnings,
        )


def test_trigger_contract_is_immutable_and_cannot_create_trade_candidate_or_ose():
    item = zone(VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE, VisionPivotZoneType.RESISTANCE_HOT_ZONE)
    context = build((candle(0, 100.15, 100.9, 99.7, 99.8),), item)
    with pytest.raises(FrozenInstanceError):
        context.trigger.trigger_type = VisionTriggerType.NO_TRIGGER
    assert context.trigger.trigger_type is VisionTriggerType.BEARISH_REJECTION
    assert not hasattr(context, "candidate_state")
    assert not hasattr(context, "option_trade_candidate")
