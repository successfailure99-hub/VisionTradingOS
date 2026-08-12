"""
Vision Pivot Method price-action trigger and acceptance intelligence.

VPM_TRIGGER_1 consumes canonical 5-minute candles plus existing Vision Method
contexts. It classifies what price did at an approved action zone. It never
creates trade candidates, invokes OSE, or modifies risk/paper execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle

from .enums import (
    VisionBOS,
    VisionBreakDirection,
    VisionBreakStrength,
    VisionCandlestickPattern,
    VisionCHoCH,
    VisionLevelQuality,
    VisionLiquiditySweep,
    VisionOpeningRangeState,
    VisionOpeningScenarioDirection,
    VisionPivotPriceRelation,
    VisionPivotReferenceKind,
    VisionPivotZoneAlignment,
    VisionPivotZoneDirectionalRole,
    VisionPivotZoneQuality,
    VisionPivotZoneStatus,
    VisionPivotZoneType,
    VisionPriceActionTriggerStageStatus,
    VisionReversalState,
    VisionStructureEventPhase,
    VisionTriggerAcceptanceState,
    VisionTriggerAlignment,
    VisionTriggerBreakState,
    VisionTriggerDirection,
    VisionTriggerInteractionState,
    VisionTriggerQuality,
    VisionTriggerRetestState,
    VisionTriggerType,
)
from .models import (
    VisionLiquidityContext,
    VisionOpeningRangeContext,
    VisionStructureContext,
    VisionStructureEventContext,
)
from .opening_assessment import VisionPivotOpeningAssessment
from .pivot_confluence import VisionPivotConfluenceContext, VisionPivotHotZone


@dataclass(frozen=True, slots=True)
class VisionPriceActionTriggerConfiguration:
    zone_interaction_tolerance_bps: float = 8.0
    wick_body_ratio: float = 2.0
    doji_body_fraction: float = 0.15
    acceptance_body_fraction: float = 0.55
    acceptance_close_buffer_bps: float = 2.0
    extreme_range_lookback: int = 5
    extreme_range_multiplier: float = 1.8
    max_zone_event_history: int = 12

    def __post_init__(self) -> None:
        for field_name in (
            "zone_interaction_tolerance_bps",
            "wick_body_ratio",
            "doji_body_fraction",
            "acceptance_body_fraction",
            "acceptance_close_buffer_bps",
            "extreme_range_multiplier",
        ):
            value = _finite_number(getattr(self, field_name), field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive.")
            object.__setattr__(self, field_name, value)
        if self.doji_body_fraction >= 1:
            raise ValueError("doji_body_fraction must be below 1.")
        if self.acceptance_body_fraction >= 1:
            raise ValueError("acceptance_body_fraction must be below 1.")
        for field_name in ("extreme_range_lookback", "max_zone_event_history"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be int.")
            if value < 1:
                raise ValueError(f"{field_name} must be positive.")


@dataclass(frozen=True, slots=True)
class VisionTriggerZoneEvent:
    zone_reference: str
    timestamp: datetime
    interaction_state: VisionTriggerInteractionState
    break_state: VisionTriggerBreakState
    acceptance_state: VisionTriggerAcceptanceState
    retest_state: VisionTriggerRetestState
    trigger_type: VisionTriggerType
    source_candle_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "zone_reference", _normalize_text(self.zone_reference, "zone_reference"))
        _validate_aware(self.timestamp, "timestamp")
        _require_enum(self.interaction_state, VisionTriggerInteractionState, "interaction_state")
        _require_enum(self.break_state, VisionTriggerBreakState, "break_state")
        _require_enum(self.acceptance_state, VisionTriggerAcceptanceState, "acceptance_state")
        _require_enum(self.retest_state, VisionTriggerRetestState, "retest_state")
        _require_enum(self.trigger_type, VisionTriggerType, "trigger_type")
        object.__setattr__(self, "source_candle_reference", _normalize_text(self.source_candle_reference, "source_candle_reference"))


@dataclass(frozen=True, slots=True)
class VisionPriceActionTrigger:
    instrument: RuntimeInstrument
    trading_date: date
    timeframe: TimeFrame
    decision_timestamp: datetime
    zone_reference: str
    zone_role: VisionPivotZoneDirectionalRole
    zone_quality: VisionPivotZoneQuality
    interaction_state: VisionTriggerInteractionState
    trigger_type: VisionTriggerType
    trigger_direction: VisionTriggerDirection
    trigger_quality: VisionTriggerQuality
    break_state: VisionTriggerBreakState
    acceptance_state: VisionTriggerAcceptanceState
    retest_state: VisionTriggerRetestState
    candlestick_pattern: VisionCandlestickPattern
    structure_alignment: VisionTriggerAlignment
    liquidity_alignment: VisionTriggerAlignment
    opening_range_alignment: VisionTriggerAlignment
    scenario_alignment: VisionTriggerAlignment
    supporting_reasons: tuple[str, ...]
    contradicting_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    source_candle_reference: str
    prior_event_reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date.")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        _validate_aware(self.decision_timestamp, "decision_timestamp")
        if self.decision_timestamp.date() != self.trading_date:
            raise ValueError("decision_timestamp trading date mismatch.")
        object.__setattr__(self, "zone_reference", _normalize_text(self.zone_reference, "zone_reference"))
        _require_enum(self.zone_role, VisionPivotZoneDirectionalRole, "zone_role")
        _require_enum(self.zone_quality, VisionPivotZoneQuality, "zone_quality")
        _require_enum(self.interaction_state, VisionTriggerInteractionState, "interaction_state")
        _require_enum(self.trigger_type, VisionTriggerType, "trigger_type")
        _require_enum(self.trigger_direction, VisionTriggerDirection, "trigger_direction")
        _require_enum(self.trigger_quality, VisionTriggerQuality, "trigger_quality")
        _require_enum(self.break_state, VisionTriggerBreakState, "break_state")
        _require_enum(self.acceptance_state, VisionTriggerAcceptanceState, "acceptance_state")
        _require_enum(self.retest_state, VisionTriggerRetestState, "retest_state")
        _require_enum(self.candlestick_pattern, VisionCandlestickPattern, "candlestick_pattern")
        _require_enum(self.structure_alignment, VisionTriggerAlignment, "structure_alignment")
        _require_enum(self.liquidity_alignment, VisionTriggerAlignment, "liquidity_alignment")
        _require_enum(self.opening_range_alignment, VisionTriggerAlignment, "opening_range_alignment")
        _require_enum(self.scenario_alignment, VisionTriggerAlignment, "scenario_alignment")
        object.__setattr__(self, "supporting_reasons", _normalize_unique_text_tuple(self.supporting_reasons, "supporting_reasons"))
        object.__setattr__(self, "contradicting_reasons", _normalize_unique_text_tuple(self.contradicting_reasons, "contradicting_reasons"))
        object.__setattr__(self, "warnings", _normalize_unique_text_tuple(self.warnings, "warnings"))
        object.__setattr__(self, "blocking_reasons", _normalize_unique_text_tuple(self.blocking_reasons, "blocking_reasons"))
        object.__setattr__(self, "source_candle_reference", _normalize_text(self.source_candle_reference, "source_candle_reference"))
        object.__setattr__(self, "prior_event_reference", _normalize_text(self.prior_event_reference, "prior_event_reference"))
        if self.trigger_type is VisionTriggerType.NO_TRIGGER and self.trigger_direction is not VisionTriggerDirection.NONE:
            raise ValueError("NO_TRIGGER requires NONE direction.")
        if self.trigger_type is VisionTriggerType.INDECISION and self.trigger_direction is not VisionTriggerDirection.NONE:
            raise ValueError("INDECISION requires NONE direction.")
        if self.trigger_quality is VisionTriggerQuality.HIGH and self.blocking_reasons:
            raise ValueError("HIGH trigger quality cannot have blocking reasons.")


@dataclass(frozen=True, slots=True)
class VisionPriceActionTriggerContext:
    instrument: RuntimeInstrument
    trading_date: date
    timeframe: TimeFrame
    timestamp: datetime
    trigger: VisionPriceActionTrigger
    event_history: tuple[VisionTriggerZoneEvent, ...]
    quality: VisionLevelQuality
    status: VisionTriggerInteractionState
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date.")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        _validate_aware(self.timestamp, "timestamp")
        if self.timestamp.date() != self.trading_date:
            raise ValueError("timestamp trading date mismatch.")
        if not isinstance(self.trigger, VisionPriceActionTrigger):
            raise TypeError("trigger must be VisionPriceActionTrigger.")
        if self.trigger.instrument is not self.instrument or self.trigger.timeframe is not self.timeframe:
            raise ValueError("trigger contract mismatch.")
        if self.trigger.trading_date != self.trading_date:
            raise ValueError("trigger trading date mismatch.")
        history = _normalize_event_history(self.event_history)
        for event in history:
            if event.timestamp.date() != self.trading_date:
                raise ValueError("event history trading date mismatch.")
        object.__setattr__(self, "event_history", history)
        _require_enum(self.quality, VisionLevelQuality, "quality")
        _require_enum(self.status, VisionTriggerInteractionState, "status")
        object.__setattr__(self, "warnings", _normalize_unique_text_tuple(self.warnings, "warnings"))


@dataclass(frozen=True, slots=True)
class VisionPriceActionTriggerStageResult:
    status: VisionPriceActionTriggerStageStatus
    trigger_context: VisionPriceActionTriggerContext | None
    failure_type: str | None
    failure_reason: str | None
    source_candle_reference: str
    trigger_zone_reference: str
    decision_timestamp: datetime
    snapshot_generation: str
    producer: str = "SymbolRuntime._current_price_action_trigger_context"
    consumer: str = "VisionMethodCalculationRequest"

    def __post_init__(self) -> None:
        if not isinstance(self.status, VisionPriceActionTriggerStageStatus):
            raise TypeError("status must be VisionPriceActionTriggerStageStatus.")
        if self.trigger_context is not None and not isinstance(self.trigger_context, VisionPriceActionTriggerContext):
            raise TypeError("trigger_context must be VisionPriceActionTriggerContext or None.")
        if self.failure_type is not None:
            object.__setattr__(self, "failure_type", _normalize_text(self.failure_type, "failure_type"))
        if self.failure_reason is not None:
            object.__setattr__(self, "failure_reason", _normalize_text(self.failure_reason, "failure_reason"))
        object.__setattr__(self, "source_candle_reference", _normalize_text(self.source_candle_reference, "source_candle_reference"))
        object.__setattr__(self, "trigger_zone_reference", _normalize_text(self.trigger_zone_reference, "trigger_zone_reference"))
        _validate_aware(self.decision_timestamp, "decision_timestamp")
        object.__setattr__(self, "snapshot_generation", _normalize_text(self.snapshot_generation, "snapshot_generation"))
        object.__setattr__(self, "producer", _normalize_text(self.producer, "producer"))
        object.__setattr__(self, "consumer", _normalize_text(self.consumer, "consumer"))
        if self.status is VisionPriceActionTriggerStageStatus.TRIGGER_ASSEMBLY_FAILED:
            if not self.failure_type or not self.failure_reason:
                raise ValueError("technical trigger failure requires failure_type and failure_reason.")
            return
        if self.failure_type is not None:
            raise ValueError("normal trigger-stage result cannot contain exception diagnostics.")


def price_action_trigger_stage_result_from_context(
    context: VisionPriceActionTriggerContext,
    *,
    snapshot_generation: str,
) -> VisionPriceActionTriggerStageResult:
    trigger = context.trigger
    if trigger.trigger_type is VisionTriggerType.INDECISION:
        status = VisionPriceActionTriggerStageStatus.EVALUATED_INDECISION
    elif trigger.trigger_type is VisionTriggerType.NO_TRIGGER:
        if trigger.interaction_state is VisionTriggerInteractionState.NO_INTERACTION:
            status = VisionPriceActionTriggerStageStatus.EVALUATED_NO_INTERACTION
        else:
            status = VisionPriceActionTriggerStageStatus.EVALUATED_NO_TRIGGER
    else:
        status = VisionPriceActionTriggerStageStatus.EVALUATED_TRIGGER
    return VisionPriceActionTriggerStageResult(
        status=status,
        trigger_context=context,
        failure_type=None,
        failure_reason=None,
        source_candle_reference=trigger.source_candle_reference,
        trigger_zone_reference=trigger.zone_reference,
        decision_timestamp=context.timestamp,
        snapshot_generation=snapshot_generation,
    )


def insufficient_price_action_trigger_stage_result(
    *,
    reason: str,
    decision_timestamp: datetime,
    source_candle_reference: str = "none",
    trigger_zone_reference: str = "none",
    snapshot_generation: str,
) -> VisionPriceActionTriggerStageResult:
    return VisionPriceActionTriggerStageResult(
        status=VisionPriceActionTriggerStageStatus.INSUFFICIENT_DATA,
        trigger_context=None,
        failure_type=None,
        failure_reason=reason,
        source_candle_reference=source_candle_reference,
        trigger_zone_reference=trigger_zone_reference,
        decision_timestamp=decision_timestamp,
        snapshot_generation=snapshot_generation,
    )


def failed_price_action_trigger_stage_result(
    *,
    exc: Exception,
    decision_timestamp: datetime,
    source_candle_reference: str = "none",
    trigger_zone_reference: str = "none",
    snapshot_generation: str,
) -> VisionPriceActionTriggerStageResult:
    return VisionPriceActionTriggerStageResult(
        status=VisionPriceActionTriggerStageStatus.TRIGGER_ASSEMBLY_FAILED,
        trigger_context=None,
        failure_type=type(exc).__name__,
        failure_reason=str(exc),
        source_candle_reference=source_candle_reference,
        trigger_zone_reference=trigger_zone_reference,
        decision_timestamp=decision_timestamp,
        snapshot_generation=snapshot_generation,
    )


@dataclass(frozen=True, slots=True)
class VisionPriceActionTriggerRequest:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    trading_date: date
    timestamp: datetime
    candles: tuple[Candle, ...]
    pivot_confluence_context: VisionPivotConfluenceContext | None
    opening_range_context: VisionOpeningRangeContext | None = None
    structure_context: VisionStructureContext | None = None
    liquidity_context: VisionLiquidityContext | None = None
    structure_event_context: VisionStructureEventContext | None = None
    pivot_opening_assessment: VisionPivotOpeningAssessment | None = None
    previous_context: VisionPriceActionTriggerContext | None = None
    configuration: VisionPriceActionTriggerConfiguration = field(default_factory=VisionPriceActionTriggerConfiguration)

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        if self.timeframe is not TimeFrame.FIVE_MINUTES:
            raise ValueError("VPM trigger evaluation requires the 5m Vision decision timeframe.")
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date.")
        _validate_aware(self.timestamp, "timestamp")
        if self.timestamp.date() != self.trading_date:
            raise ValueError("timestamp trading date mismatch.")
        if not isinstance(self.candles, tuple):
            raise TypeError("candles must be tuple.")
        if self.pivot_confluence_context is not None and not isinstance(self.pivot_confluence_context, VisionPivotConfluenceContext):
            raise TypeError("pivot_confluence_context must be VisionPivotConfluenceContext or None.")
        for field_name, expected_type in (
            ("opening_range_context", VisionOpeningRangeContext),
            ("structure_context", VisionStructureContext),
            ("liquidity_context", VisionLiquidityContext),
            ("structure_event_context", VisionStructureEventContext),
            ("pivot_opening_assessment", VisionPivotOpeningAssessment),
            ("previous_context", VisionPriceActionTriggerContext),
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, expected_type):
                raise TypeError(f"{field_name} must be {expected_type.__name__} or None.")
        if not isinstance(self.configuration, VisionPriceActionTriggerConfiguration):
            raise TypeError("configuration must be VisionPriceActionTriggerConfiguration.")


def build_price_action_trigger_context(request: VisionPriceActionTriggerRequest) -> VisionPriceActionTriggerContext:
    validate_price_action_trigger_request(request)
    ordered = tuple(sorted(request.candles, key=lambda candle: (candle.start_time, candle.end_time)))
    latest = ordered[-1] if ordered else None
    if latest is None:
        trigger = _no_trigger(request, "No closed 5m candle is available")
        return _context(request, trigger, ())
    zone = _select_zone(request)
    if zone is None:
        trigger = _no_trigger(request, "No active meaningful hot zone is available", candle=latest)
        return _context(request, trigger, ())

    prior_events = _prior_events(request, zone)
    prior_event = prior_events[-1] if prior_events else None
    pattern = _candlestick_pattern(ordered, zone, request.configuration)
    interaction, break_state, acceptance_state, retest_state = _classify_interaction(
        latest,
        zone,
        prior_event,
        request.configuration,
    )
    trigger_type, direction = _trigger_type(
        latest,
        zone,
        interaction,
        break_state,
        acceptance_state,
        retest_state,
        pattern,
        prior_event,
        request,
    )
    structure_alignment = _structure_alignment(direction, request.structure_event_context, request.structure_context)
    liquidity_alignment = _liquidity_alignment(direction, request.liquidity_context, zone, interaction)
    opening_range_alignment = _opening_range_alignment(direction, request.opening_range_context, break_state, acceptance_state)
    scenario_alignment = _scenario_alignment(direction, request.pivot_opening_assessment)
    supporting, contradicting, warnings, blocking = _reasons(
        zone,
        interaction,
        trigger_type,
        direction,
        pattern,
        structure_alignment,
        liquidity_alignment,
        opening_range_alignment,
        scenario_alignment,
    )
    quality = _trigger_quality(
        zone,
        trigger_type,
        structure_alignment,
        liquidity_alignment,
        opening_range_alignment,
        scenario_alignment,
        pattern,
        blocking,
    )
    trigger = VisionPriceActionTrigger(
        instrument=request.instrument,
        trading_date=request.trading_date,
        timeframe=request.timeframe,
        decision_timestamp=latest.end_time,
        zone_reference=_zone_reference(zone),
        zone_role=zone.directional_role,
        zone_quality=zone.quality,
        interaction_state=interaction,
        trigger_type=trigger_type,
        trigger_direction=direction,
        trigger_quality=quality,
        break_state=break_state,
        acceptance_state=acceptance_state,
        retest_state=retest_state,
        candlestick_pattern=pattern,
        structure_alignment=structure_alignment,
        liquidity_alignment=liquidity_alignment,
        opening_range_alignment=opening_range_alignment,
        scenario_alignment=scenario_alignment,
        supporting_reasons=supporting,
        contradicting_reasons=contradicting,
        warnings=warnings,
        blocking_reasons=blocking,
        source_candle_reference=_candle_reference(latest),
        prior_event_reference=_event_reference(prior_event),
    )
    event = VisionTriggerZoneEvent(
        zone_reference=trigger.zone_reference,
        timestamp=trigger.decision_timestamp,
        interaction_state=trigger.interaction_state,
        break_state=trigger.break_state,
        acceptance_state=trigger.acceptance_state,
        retest_state=trigger.retest_state,
        trigger_type=trigger.trigger_type,
        source_candle_reference=trigger.source_candle_reference,
    )
    history = _append_event(prior_events, event, request.configuration.max_zone_event_history)
    return _context(request, trigger, history)


def validate_price_action_trigger_request(request: VisionPriceActionTriggerRequest) -> VisionPriceActionTriggerRequest:
    if not isinstance(request, VisionPriceActionTriggerRequest):
        raise TypeError("request must be VisionPriceActionTriggerRequest.")
    previous: Candle | None = None
    for candle in sorted(request.candles, key=lambda item: (item.start_time, item.end_time)):
        _validate_candle(candle, request)
        if previous is not None and candle.start_time < previous.end_time:
            raise ValueError("invalid candle sequence.")
        previous = candle
    for context_name in ("pivot_confluence_context", "previous_context"):
        context = getattr(request, context_name)
        if context is None:
            continue
        if context.instrument is not request.instrument:
            raise ValueError(f"{context_name} instrument mismatch.")
        if context.timeframe is not request.timeframe:
            raise ValueError(f"{context_name} timeframe mismatch.")
        if context.trading_date != request.trading_date:
            raise ValueError(f"{context_name} trading date mismatch.")
        if context.timestamp > request.timestamp:
            raise ValueError(f"{context_name} timestamp cannot be after request timestamp.")
    return request


def _select_zone(request: VisionPriceActionTriggerRequest) -> VisionPivotHotZone | None:
    context = request.pivot_confluence_context
    if context is None:
        return None
    active = tuple(zone for zone in context.hot_zones if zone.status is VisionPivotZoneStatus.ACTIVE)
    if not active:
        return None
    return sorted(active, key=lambda zone: (_zone_distance_rank(zone), _zone_rank(zone), zone.zone_center))[0]


def _zone_distance_rank(zone: VisionPivotHotZone) -> int:
    relation = zone.current_price_relation
    if relation is VisionPivotPriceRelation.INSIDE:
        return 0
    if relation is VisionPivotPriceRelation.APPROACHING:
        return 1
    return 2


def _zone_rank(zone: VisionPivotHotZone) -> tuple[int, int, int]:
    quality = {
        VisionPivotZoneQuality.HIGH: 3,
        VisionPivotZoneQuality.VERY_HIGH: 4,
        VisionPivotZoneQuality.MEDIUM: 2,
        VisionPivotZoneQuality.LOW: 1,
    }[zone.quality]
    alignment = {
        VisionPivotZoneAlignment.ALIGNED: 4,
        VisionPivotZoneAlignment.PARTIAL: 3,
        VisionPivotZoneAlignment.NEUTRAL: 2,
        VisionPivotZoneAlignment.UNRESOLVED: 1,
        VisionPivotZoneAlignment.OPPOSED: 0,
    }[zone.active_scenario_alignment]
    return (-quality, -zone.independent_family_count, -alignment)


def _prior_events(request: VisionPriceActionTriggerRequest, zone: VisionPivotHotZone) -> tuple[VisionTriggerZoneEvent, ...]:
    previous = request.previous_context
    if previous is None:
        return ()
    reference = _zone_reference(zone)
    return tuple(event for event in previous.event_history if event.zone_reference == reference)


def _classify_interaction(
    candle: Candle,
    zone: VisionPivotHotZone,
    prior_event: VisionTriggerZoneEvent | None,
    config: VisionPriceActionTriggerConfiguration,
) -> tuple[
    VisionTriggerInteractionState,
    VisionTriggerBreakState,
    VisionTriggerAcceptanceState,
    VisionTriggerRetestState,
]:
    low, high = zone.zone_low, zone.zone_high
    tolerance = _tolerance(zone.zone_center, config.zone_interaction_tolerance_bps)
    touched = candle.high >= low and candle.low <= high
    near = low - tolerance <= candle.high and candle.low <= high + tolerance
    accepted_up = _accepted_up(candle, zone, config)
    accepted_down = _accepted_down(candle, zone, config)
    prior_accepted_up = prior_event is not None and prior_event.acceptance_state is VisionTriggerAcceptanceState.ACCEPTED_UP
    prior_accepted_down = prior_event is not None and prior_event.acceptance_state is VisionTriggerAcceptanceState.ACCEPTED_DOWN

    if prior_accepted_up and candle.low <= high and candle.close >= high:
        return (
            VisionTriggerInteractionState.HOLDING,
            VisionTriggerBreakState.BROKEN_UP,
            VisionTriggerAcceptanceState.ACCEPTED_UP,
            VisionTriggerRetestState.RETEST_HOLD,
        )
    if prior_accepted_down and candle.high >= low and candle.close <= low:
        return (
            VisionTriggerInteractionState.HOLDING,
            VisionTriggerBreakState.BROKEN_DOWN,
            VisionTriggerAcceptanceState.ACCEPTED_DOWN,
            VisionTriggerRetestState.RETEST_HOLD,
        )
    if prior_accepted_up and candle.close < low:
        return (
            VisionTriggerInteractionState.FAILING,
            VisionTriggerBreakState.BROKEN_UP,
            VisionTriggerAcceptanceState.FAILED_UP,
            VisionTriggerRetestState.RETEST_FAILURE,
        )
    if prior_accepted_down and candle.close > high:
        return (
            VisionTriggerInteractionState.FAILING,
            VisionTriggerBreakState.BROKEN_DOWN,
            VisionTriggerAcceptanceState.FAILED_DOWN,
            VisionTriggerRetestState.RETEST_FAILURE,
        )
    if accepted_up:
        return (
            VisionTriggerInteractionState.ACCEPTED,
            VisionTriggerBreakState.BROKEN_UP,
            VisionTriggerAcceptanceState.ACCEPTED_UP,
            VisionTriggerRetestState.NONE,
        )
    if accepted_down:
        return (
            VisionTriggerInteractionState.ACCEPTED,
            VisionTriggerBreakState.BROKEN_DOWN,
            VisionTriggerAcceptanceState.ACCEPTED_DOWN,
            VisionTriggerRetestState.NONE,
        )
    if candle.high > high and candle.close < low:
        return (
            VisionTriggerInteractionState.REJECTING,
            VisionTriggerBreakState.BROKEN_UP,
            VisionTriggerAcceptanceState.FAILED_UP,
            VisionTriggerRetestState.NONE,
        )
    if candle.low < low and candle.close > high:
        return (
            VisionTriggerInteractionState.REJECTING,
            VisionTriggerBreakState.BROKEN_DOWN,
            VisionTriggerAcceptanceState.FAILED_DOWN,
            VisionTriggerRetestState.NONE,
        )
    if candle.close > high:
        return (
            VisionTriggerInteractionState.BROKEN,
            VisionTriggerBreakState.BROKEN_UP,
            VisionTriggerAcceptanceState.WAITING_FOR_ACCEPTANCE,
            VisionTriggerRetestState.NONE,
        )
    if candle.close < low:
        return (
            VisionTriggerInteractionState.BROKEN,
            VisionTriggerBreakState.BROKEN_DOWN,
            VisionTriggerAcceptanceState.WAITING_FOR_ACCEPTANCE,
            VisionTriggerRetestState.NONE,
        )
    if touched:
        if candle.high > high or candle.low < low:
            return (
                VisionTriggerInteractionState.PENETRATING,
                VisionTriggerBreakState.NONE,
                VisionTriggerAcceptanceState.NONE,
                VisionTriggerRetestState.NONE,
            )
        return (
            VisionTriggerInteractionState.TESTING,
            VisionTriggerBreakState.NONE,
            VisionTriggerAcceptanceState.NONE,
            VisionTriggerRetestState.NONE,
        )
    if near:
        return (
            VisionTriggerInteractionState.APPROACHING,
            VisionTriggerBreakState.NONE,
            VisionTriggerAcceptanceState.NONE,
            VisionTriggerRetestState.NONE,
        )
    return (
        VisionTriggerInteractionState.NO_INTERACTION,
        VisionTriggerBreakState.NONE,
        VisionTriggerAcceptanceState.NONE,
        VisionTriggerRetestState.NONE,
    )


def _accepted_up(candle: Candle, zone: VisionPivotHotZone, config: VisionPriceActionTriggerConfiguration) -> bool:
    body = abs(candle.close - candle.open)
    full_range = max(candle.high - candle.low, 1e-9)
    buffer = _tolerance(zone.zone_center, config.acceptance_close_buffer_bps)
    return candle.close > zone.zone_high + buffer and candle.close > candle.open and body / full_range >= config.acceptance_body_fraction


def _accepted_down(candle: Candle, zone: VisionPivotHotZone, config: VisionPriceActionTriggerConfiguration) -> bool:
    body = abs(candle.close - candle.open)
    full_range = max(candle.high - candle.low, 1e-9)
    buffer = _tolerance(zone.zone_center, config.acceptance_close_buffer_bps)
    return candle.close < zone.zone_low - buffer and candle.close < candle.open and body / full_range >= config.acceptance_body_fraction


def _trigger_type(
    candle: Candle,
    zone: VisionPivotHotZone,
    interaction: VisionTriggerInteractionState,
    break_state: VisionTriggerBreakState,
    acceptance_state: VisionTriggerAcceptanceState,
    retest_state: VisionTriggerRetestState,
    pattern: VisionCandlestickPattern,
    prior_event: VisionTriggerZoneEvent | None,
    request: VisionPriceActionTriggerRequest,
) -> tuple[VisionTriggerType, VisionTriggerDirection]:
    if pattern is VisionCandlestickPattern.DOJI and interaction in {VisionTriggerInteractionState.TESTING, VisionTriggerInteractionState.PENETRATING}:
        return VisionTriggerType.INDECISION, VisionTriggerDirection.NONE
    if retest_state is VisionTriggerRetestState.RETEST_HOLD:
        if acceptance_state is VisionTriggerAcceptanceState.ACCEPTED_UP:
            return VisionTriggerType.BULLISH_RETEST_HOLD, VisionTriggerDirection.BULLISH
        if acceptance_state is VisionTriggerAcceptanceState.ACCEPTED_DOWN:
            return VisionTriggerType.BEARISH_RETEST_HOLD, VisionTriggerDirection.BEARISH
    if retest_state is VisionTriggerRetestState.RETEST_FAILURE:
        if acceptance_state is VisionTriggerAcceptanceState.FAILED_UP:
            return VisionTriggerType.BEARISH_FAILED_BREAKOUT, VisionTriggerDirection.BEARISH
        if acceptance_state is VisionTriggerAcceptanceState.FAILED_DOWN:
            return VisionTriggerType.BULLISH_FAILED_BREAKOUT, VisionTriggerDirection.BULLISH
    if acceptance_state is VisionTriggerAcceptanceState.FAILED_UP:
        if not _initiative_zone(zone) and _resistance_role(zone):
            return VisionTriggerType.BEARISH_REJECTION, VisionTriggerDirection.BEARISH
        return VisionTriggerType.BEARISH_FAILED_BREAKOUT, VisionTriggerDirection.BEARISH
    if acceptance_state is VisionTriggerAcceptanceState.FAILED_DOWN:
        if not _initiative_zone(zone) and _support_role(zone):
            return VisionTriggerType.BULLISH_REJECTION, VisionTriggerDirection.BULLISH
        return VisionTriggerType.BULLISH_FAILED_BREAKOUT, VisionTriggerDirection.BULLISH
    if prior_event is not None and prior_event.acceptance_state in {
        VisionTriggerAcceptanceState.ACCEPTED_UP,
        VisionTriggerAcceptanceState.ACCEPTED_DOWN,
    }:
        if acceptance_state is prior_event.acceptance_state and _structure_supports_acceptance(request.structure_event_context, acceptance_state):
            if acceptance_state is VisionTriggerAcceptanceState.ACCEPTED_UP:
                return VisionTriggerType.BULLISH_CONTINUATION, VisionTriggerDirection.BULLISH
            return VisionTriggerType.BEARISH_CONTINUATION, VisionTriggerDirection.BEARISH
    if acceptance_state is VisionTriggerAcceptanceState.ACCEPTED_UP and _initiative_zone(zone):
        return VisionTriggerType.BULLISH_INITIATIVE_BREAKOUT, VisionTriggerDirection.BULLISH
    if acceptance_state is VisionTriggerAcceptanceState.ACCEPTED_DOWN and _initiative_zone(zone):
        return VisionTriggerType.BEARISH_INITIATIVE_BREAKOUT, VisionTriggerDirection.BEARISH
    if interaction is VisionTriggerInteractionState.REJECTING:
        if _bullish_rejection(candle, zone, pattern):
            return VisionTriggerType.BULLISH_REJECTION, VisionTriggerDirection.BULLISH
        if _bearish_rejection(candle, zone, pattern):
            return VisionTriggerType.BEARISH_REJECTION, VisionTriggerDirection.BEARISH
    return VisionTriggerType.NO_TRIGGER, VisionTriggerDirection.NONE


def _candlestick_pattern(
    candles: tuple[Candle, ...],
    zone: VisionPivotHotZone,
    config: VisionPriceActionTriggerConfiguration,
) -> VisionCandlestickPattern:
    latest = candles[-1]
    body = abs(latest.close - latest.open)
    candle_range = max(latest.high - latest.low, 1e-9)
    if body / candle_range <= config.doji_body_fraction:
        return VisionCandlestickPattern.DOJI
    lower_wick = min(latest.open, latest.close) - latest.low
    upper_wick = latest.high - max(latest.open, latest.close)
    if lower_wick >= max(body, 1e-9) * config.wick_body_ratio and latest.close > latest.open and _support_role(zone):
        return VisionCandlestickPattern.BULLISH_WICK_REVERSAL
    if upper_wick >= max(body, 1e-9) * config.wick_body_ratio and latest.close < latest.open and _resistance_role(zone):
        return VisionCandlestickPattern.BEARISH_WICK_REVERSAL
    if len(candles) >= 2:
        previous = candles[-2]
        if latest.low < previous.low and latest.close > previous.high and _support_role(zone):
            return VisionCandlestickPattern.BULLISH_OUTSIDE_REVERSAL
        if latest.high > previous.high and latest.close < previous.low and _resistance_role(zone):
            return VisionCandlestickPattern.BEARISH_OUTSIDE_REVERSAL
    if len(candles) >= config.extreme_range_lookback + 2:
        prior = candles[-2]
        ranges = tuple(item.high - item.low for item in candles[-(config.extreme_range_lookback + 2) : -2])
        average = sum(ranges) / len(ranges)
        if prior.high - prior.low >= average * config.extreme_range_multiplier:
            if prior.close < prior.open and latest.close > latest.open and latest.close > prior.open and _support_role(zone):
                return VisionCandlestickPattern.BULLISH_EXTREME_REVERSAL
            if prior.close > prior.open and latest.close < latest.open and latest.close < prior.open and _resistance_role(zone):
                return VisionCandlestickPattern.BEARISH_EXTREME_REVERSAL
    return VisionCandlestickPattern.NONE


def _bullish_rejection(candle: Candle, zone: VisionPivotHotZone, pattern: VisionCandlestickPattern) -> bool:
    return _support_role(zone) and candle.low < zone.zone_low and candle.close > zone.zone_high and pattern in {
        VisionCandlestickPattern.BULLISH_WICK_REVERSAL,
        VisionCandlestickPattern.BULLISH_OUTSIDE_REVERSAL,
        VisionCandlestickPattern.BULLISH_EXTREME_REVERSAL,
        VisionCandlestickPattern.NONE,
    }


def _bearish_rejection(candle: Candle, zone: VisionPivotHotZone, pattern: VisionCandlestickPattern) -> bool:
    return _resistance_role(zone) and candle.high > zone.zone_high and candle.close < zone.zone_low and pattern in {
        VisionCandlestickPattern.BEARISH_WICK_REVERSAL,
        VisionCandlestickPattern.BEARISH_OUTSIDE_REVERSAL,
        VisionCandlestickPattern.BEARISH_EXTREME_REVERSAL,
        VisionCandlestickPattern.NONE,
    }


def _support_role(zone: VisionPivotHotZone) -> bool:
    return zone.directional_role in {VisionPivotZoneDirectionalRole.BULLISH_SUPPORT, VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE}


def _resistance_role(zone: VisionPivotHotZone) -> bool:
    return zone.directional_role in {VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE, VisionPivotZoneDirectionalRole.BREAKDOWN_DOWNSIDE}


def _initiative_zone(zone: VisionPivotHotZone) -> bool:
    return zone.zone_type is VisionPivotZoneType.BREAKOUT_DECISION_ZONE or zone.directional_role in {
        VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE,
        VisionPivotZoneDirectionalRole.BREAKDOWN_DOWNSIDE,
    }


def _structure_supports_acceptance(
    context: VisionStructureEventContext | None,
    acceptance: VisionTriggerAcceptanceState,
) -> bool:
    if context is None:
        return False
    if acceptance is VisionTriggerAcceptanceState.ACCEPTED_UP:
        return context.bos is VisionBOS.BULLISH_BOS or context.choch is VisionCHoCH.BULLISH_CHOCH
    if acceptance is VisionTriggerAcceptanceState.ACCEPTED_DOWN:
        return context.bos is VisionBOS.BEARISH_BOS or context.choch is VisionCHoCH.BEARISH_CHOCH
    return False


def _structure_alignment(
    direction: VisionTriggerDirection,
    event: VisionStructureEventContext | None,
    structure: VisionStructureContext | None,
) -> VisionTriggerAlignment:
    if direction is VisionTriggerDirection.NONE:
        return VisionTriggerAlignment.NEUTRAL
    if event is not None:
        if direction is VisionTriggerDirection.BULLISH and event.bos is VisionBOS.BULLISH_BOS:
            return VisionTriggerAlignment.ALIGNED
        if direction is VisionTriggerDirection.BEARISH and event.bos is VisionBOS.BEARISH_BOS:
            return VisionTriggerAlignment.ALIGNED
        if direction is VisionTriggerDirection.BULLISH and event.choch is VisionCHoCH.BULLISH_CHOCH:
            return VisionTriggerAlignment.SUPPORTING
        if direction is VisionTriggerDirection.BEARISH and event.choch is VisionCHoCH.BEARISH_CHOCH:
            return VisionTriggerAlignment.SUPPORTING
        if event.continuation is not VisionStructureEventPhase.NONE or event.reversal is not VisionReversalState.NONE:
            return VisionTriggerAlignment.CONTRADICTING
    if structure is None:
        return VisionTriggerAlignment.UNAVAILABLE
    return VisionTriggerAlignment.NEUTRAL


def _liquidity_alignment(
    direction: VisionTriggerDirection,
    context: VisionLiquidityContext | None,
    zone: VisionPivotHotZone,
    interaction: VisionTriggerInteractionState,
) -> VisionTriggerAlignment:
    if context is None or context.quality is VisionLevelQuality.INSUFFICIENT:
        return VisionTriggerAlignment.UNAVAILABLE
    if direction is VisionTriggerDirection.BULLISH:
        if context.liquidity_sweep is VisionLiquiditySweep.SELL_SIDE_SWEEP:
            return VisionTriggerAlignment.ALIGNED
        if context.liquidity_sweep is VisionLiquiditySweep.BUY_SIDE_SWEEP and zone.directional_role is VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE:
            return VisionTriggerAlignment.CONTRADICTING
    if direction is VisionTriggerDirection.BEARISH:
        if context.liquidity_sweep is VisionLiquiditySweep.BUY_SIDE_SWEEP:
            return VisionTriggerAlignment.ALIGNED
        if context.liquidity_sweep is VisionLiquiditySweep.SELL_SIDE_SWEEP and zone.directional_role is VisionPivotZoneDirectionalRole.BULLISH_SUPPORT:
            return VisionTriggerAlignment.CONTRADICTING
    if context.liquidity_sweep is not VisionLiquiditySweep.NONE and interaction in {
        VisionTriggerInteractionState.REJECTING,
        VisionTriggerInteractionState.FAILING,
    }:
        return VisionTriggerAlignment.SUPPORTING
    return VisionTriggerAlignment.NEUTRAL


def _opening_range_alignment(
    direction: VisionTriggerDirection,
    context: VisionOpeningRangeContext | None,
    break_state: VisionTriggerBreakState,
    acceptance: VisionTriggerAcceptanceState,
) -> VisionTriggerAlignment:
    if context is None or context.quality is VisionLevelQuality.INSUFFICIENT:
        return VisionTriggerAlignment.UNAVAILABLE
    if direction is VisionTriggerDirection.BULLISH and context.break_direction is VisionBreakDirection.UP:
        return VisionTriggerAlignment.ALIGNED if acceptance is VisionTriggerAcceptanceState.ACCEPTED_UP else VisionTriggerAlignment.SUPPORTING
    if direction is VisionTriggerDirection.BEARISH and context.break_direction is VisionBreakDirection.DOWN:
        return VisionTriggerAlignment.ALIGNED if acceptance is VisionTriggerAcceptanceState.ACCEPTED_DOWN else VisionTriggerAlignment.SUPPORTING
    if context.false_break and break_state is not VisionTriggerBreakState.NONE:
        return VisionTriggerAlignment.SUPPORTING
    return VisionTriggerAlignment.NEUTRAL


def _scenario_alignment(
    direction: VisionTriggerDirection,
    assessment: VisionPivotOpeningAssessment | None,
) -> VisionTriggerAlignment:
    if assessment is None:
        return VisionTriggerAlignment.UNAVAILABLE
    if direction is VisionTriggerDirection.NONE:
        return VisionTriggerAlignment.NEUTRAL
    if direction is VisionTriggerDirection.BULLISH:
        if assessment.scenario_direction is VisionOpeningScenarioDirection.BULLISH:
            return VisionTriggerAlignment.ALIGNED
        if assessment.scenario_direction is VisionOpeningScenarioDirection.BEARISH:
            return VisionTriggerAlignment.CONTRADICTING
    if direction is VisionTriggerDirection.BEARISH:
        if assessment.scenario_direction is VisionOpeningScenarioDirection.BEARISH:
            return VisionTriggerAlignment.ALIGNED
        if assessment.scenario_direction is VisionOpeningScenarioDirection.BULLISH:
            return VisionTriggerAlignment.CONTRADICTING
    return VisionTriggerAlignment.NEUTRAL


def _trigger_quality(
    zone: VisionPivotHotZone,
    trigger_type: VisionTriggerType,
    structure: VisionTriggerAlignment,
    liquidity: VisionTriggerAlignment,
    opening_range: VisionTriggerAlignment,
    scenario: VisionTriggerAlignment,
    pattern: VisionCandlestickPattern,
    blocking: tuple[str, ...],
) -> VisionTriggerQuality:
    if trigger_type in {VisionTriggerType.NO_TRIGGER, VisionTriggerType.INDECISION}:
        return VisionTriggerQuality.INVALID if trigger_type is VisionTriggerType.NO_TRIGGER else VisionTriggerQuality.LOW
    if blocking:
        return VisionTriggerQuality.LOW
    score = 0
    if zone.quality in {VisionPivotZoneQuality.HIGH, VisionPivotZoneQuality.VERY_HIGH}:
        score += 2
    elif zone.quality is VisionPivotZoneQuality.MEDIUM:
        score += 1
    for alignment in (structure, liquidity, opening_range, scenario):
        if alignment is VisionTriggerAlignment.ALIGNED:
            score += 2
        elif alignment is VisionTriggerAlignment.SUPPORTING:
            score += 1
        elif alignment is VisionTriggerAlignment.CONTRADICTING:
            score -= 2
    if pattern is not VisionCandlestickPattern.NONE:
        score += 1
    if score >= 5:
        return VisionTriggerQuality.HIGH
    if score >= 2:
        return VisionTriggerQuality.MEDIUM
    return VisionTriggerQuality.LOW


def _reasons(
    zone: VisionPivotHotZone,
    interaction: VisionTriggerInteractionState,
    trigger_type: VisionTriggerType,
    direction: VisionTriggerDirection,
    pattern: VisionCandlestickPattern,
    structure: VisionTriggerAlignment,
    liquidity: VisionTriggerAlignment,
    opening_range: VisionTriggerAlignment,
    scenario: VisionTriggerAlignment,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    supporting = [
        f"Zone {zone.directional_role.value} {zone.zone_low:.2f}-{zone.zone_high:.2f}",
        f"Interaction {interaction.value}",
    ]
    contradicting: list[str] = []
    warnings: list[str] = []
    blocking: list[str] = []
    if trigger_type is VisionTriggerType.NO_TRIGGER:
        blocking.append("Price action trigger not confirmed")
    if trigger_type is VisionTriggerType.INDECISION:
        warnings.append("Doji marks indecision only")
    if pattern is not VisionCandlestickPattern.NONE:
        supporting.append(f"Pattern {pattern.value}")
    for name, value in (
        ("Structure", structure),
        ("Liquidity", liquidity),
        ("Opening range", opening_range),
        ("Scenario", scenario),
    ):
        if value in {VisionTriggerAlignment.ALIGNED, VisionTriggerAlignment.SUPPORTING}:
            supporting.append(f"{name} {value.value}")
        elif value is VisionTriggerAlignment.CONTRADICTING:
            contradicting.append(f"{name} contradicts trigger")
    if zone.status is VisionPivotZoneStatus.CONSUMED:
        warnings.append("Consumed zone cannot improve trigger quality")
    if direction is VisionTriggerDirection.NONE and trigger_type not in {VisionTriggerType.NO_TRIGGER, VisionTriggerType.INDECISION}:
        blocking.append("Trigger direction unavailable")
    return (
        _dedupe(supporting),
        _dedupe(contradicting),
        _dedupe(warnings),
        _dedupe(blocking),
    )


def _context(
    request: VisionPriceActionTriggerRequest,
    trigger: VisionPriceActionTrigger,
    event_history: tuple[VisionTriggerZoneEvent, ...],
) -> VisionPriceActionTriggerContext:
    quality = VisionLevelQuality.FULL if trigger.trigger_type not in {VisionTriggerType.NO_TRIGGER, VisionTriggerType.INDECISION} else VisionLevelQuality.PARTIAL
    if trigger.trigger_type is VisionTriggerType.NO_TRIGGER and trigger.interaction_state is VisionTriggerInteractionState.NO_INTERACTION:
        quality = VisionLevelQuality.INSUFFICIENT
    return VisionPriceActionTriggerContext(
        instrument=request.instrument,
        trading_date=request.trading_date,
        timeframe=request.timeframe,
        timestamp=trigger.decision_timestamp,
        trigger=trigger,
        event_history=event_history,
        quality=quality,
        status=trigger.interaction_state,
        warnings=trigger.warnings,
    )


def _no_trigger(
    request: VisionPriceActionTriggerRequest,
    reason: str,
    *,
    candle: Candle | None = None,
) -> VisionPriceActionTrigger:
    timestamp = candle.end_time if candle is not None else request.timestamp
    return VisionPriceActionTrigger(
        instrument=request.instrument,
        trading_date=request.trading_date,
        timeframe=request.timeframe,
        decision_timestamp=timestamp,
        zone_reference="none",
        zone_role=VisionPivotZoneDirectionalRole.NEUTRAL,
        zone_quality=VisionPivotZoneQuality.LOW,
        interaction_state=VisionTriggerInteractionState.NO_INTERACTION,
        trigger_type=VisionTriggerType.NO_TRIGGER,
        trigger_direction=VisionTriggerDirection.NONE,
        trigger_quality=VisionTriggerQuality.INVALID,
        break_state=VisionTriggerBreakState.NONE,
        acceptance_state=VisionTriggerAcceptanceState.NONE,
        retest_state=VisionTriggerRetestState.NONE,
        candlestick_pattern=VisionCandlestickPattern.NONE,
        structure_alignment=VisionTriggerAlignment.UNAVAILABLE,
        liquidity_alignment=VisionTriggerAlignment.UNAVAILABLE,
        opening_range_alignment=VisionTriggerAlignment.UNAVAILABLE,
        scenario_alignment=VisionTriggerAlignment.UNAVAILABLE,
        supporting_reasons=(),
        contradicting_reasons=(),
        warnings=(),
        blocking_reasons=(reason,),
        source_candle_reference=_candle_reference(candle) if candle is not None else "none",
        prior_event_reference="none",
    )


def _append_event(
    history: tuple[VisionTriggerZoneEvent, ...],
    event: VisionTriggerZoneEvent,
    limit: int,
) -> tuple[VisionTriggerZoneEvent, ...]:
    if history and history[-1].source_candle_reference == event.source_candle_reference:
        return history
    return (*history, event)[-limit:]


def _normalize_event_history(values: tuple[VisionTriggerZoneEvent, ...]) -> tuple[VisionTriggerZoneEvent, ...]:
    if not isinstance(values, tuple):
        raise TypeError("event_history must be tuple.")
    previous: datetime | None = None
    for value in values:
        if not isinstance(value, VisionTriggerZoneEvent):
            raise TypeError("event_history must contain VisionTriggerZoneEvent values.")
        if previous is not None and value.timestamp < previous:
            raise ValueError("event_history must be ordered.")
        previous = value.timestamp
    return values


def _zone_reference(zone: VisionPivotHotZone) -> str:
    members = ",".join(member.kind.value for member in zone.member_references)
    return f"hot_zone:{zone.trading_date.isoformat()}:{zone.zone_low:.4f}:{zone.zone_high:.4f}:{zone.directional_role.value}:{members}"


def _event_reference(event: VisionTriggerZoneEvent | None) -> str:
    if event is None:
        return "none"
    return f"{event.zone_reference}:{event.timestamp.isoformat()}:{event.interaction_state.value}:{event.trigger_type.value}"


def _candle_reference(candle: Candle | None) -> str:
    if candle is None:
        return "none"
    return f"candle:{candle.symbol}:{candle.timeframe}:{candle.start_time.isoformat()}:{candle.end_time.isoformat()}"


def _validate_candle(candle: Candle, request: VisionPriceActionTriggerRequest) -> None:
    if not isinstance(candle, Candle):
        raise TypeError("candles must contain Candle objects.")
    if candle.symbol != request.instrument.value:
        raise ValueError("candle instrument mismatch.")
    if candle.timeframe != request.timeframe.value:
        raise ValueError("candle timeframe mismatch.")
    _validate_aware(candle.start_time, "candle.start_time")
    _validate_aware(candle.end_time, "candle.end_time")
    if candle.start_time.utcoffset() != request.timestamp.utcoffset() or candle.end_time.utcoffset() != request.timestamp.utcoffset():
        raise ValueError("candle timezone mismatch.")
    if candle.start_time.date() != request.trading_date or candle.end_time.date() != request.trading_date:
        raise ValueError("candle trading date mismatch.")
    if candle.end_time <= candle.start_time:
        raise ValueError("candle end_time must be after start_time.")
    if candle.end_time > request.timestamp:
        raise ValueError("candle cannot close after request timestamp.")
    if candle.high < candle.low:
        raise ValueError("candle high cannot be below low.")
    if not candle.low <= candle.open <= candle.high:
        raise ValueError("candle open must be inside high/low range.")
    if not candle.low <= candle.close <= candle.high:
        raise ValueError("candle close must be inside high/low range.")


def _tolerance(price: float, bps: float) -> float:
    return abs(price) * bps / 10000.0


def _finite_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric.")
    normalized = float(value)
    if normalized != normalized or normalized in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} must be finite.")
    return normalized


def _normalize_unique_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple.")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_text(value, field_name)
        key = normalized.casefold()
        if key in seen:
            raise ValueError(f"{field_name} cannot contain duplicate values.")
        seen.add(key)
        result.append(normalized)
    return tuple(result)


def _dedupe(values: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return tuple(result)


def _require_enum(value, expected_type, field_name: str) -> None:
    if not isinstance(value, expected_type):
        raise TypeError(f"{field_name} must be {expected_type.__name__}.")


def _normalize_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text.")
    return value.strip()


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
