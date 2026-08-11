"""
Immutable Vision Method V1 model contracts.

VM-01 defines methodology contracts only. These models reference existing
evidence contexts without recalculating indicator values or producing trades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame

from .enums import (
    VisionBOS,
    VisionBreakerBlockState,
    VisionBreakStrength,
    VisionBreakDirection,
    VisionCHoCH,
    VisionCPRRelation,
    VisionCamarillaZone,
    VisionCandidateState,
    VisionChaseRisk,
    VisionContextAssemblyStatus,
    VisionDirectionQuality,
    VisionEntryLocationState,
    VisionFairValueGapDirection,
    VisionGapType,
    VisionLevelQuality,
    VisionLiquidityPool,
    VisionLiquiditySweep,
    VisionMarketRegime,
    VisionMitigationState,
    VisionMoveMaturity,
    VisionOpeningLocation,
    VisionOpeningRangeState,
    VisionOrderBlockDirection,
    VisionPivotCombinedContext,
    VisionPivotDirectionalPrior,
    VisionPivotRelationship,
    VisionPivotTendency,
    VisionPivotWidthState,
    VisionPreviousDayRelation,
    VisionRangeLocation,
    VisionReversalState,
    VisionSetupQuality,
    VisionSetupType,
    VisionMSS,
    VisionStructureEventPhase,
    VisionStructurePattern,
    VisionStructureTrend,
    VisionOptionConfirmation,
    VisionSweepDirection,
    VisionSwingType,
    VisionVWAPRelation,
)
from .pivot_context import VisionPivotFlightPlan

if TYPE_CHECKING:
    from .opening_assessment import VisionPivotOpeningAssessment
    from .pivot_confluence import VisionPivotConfluenceContext


@dataclass(frozen=True, slots=True)
class VisionContextAssemblyFailure:
    stage: str
    status: VisionContextAssemblyStatus
    failure_reason: str
    validation_message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", _normalize_text(self.stage, "stage"))
        if not isinstance(self.status, VisionContextAssemblyStatus):
            raise TypeError("status must be VisionContextAssemblyStatus.")
        object.__setattr__(self, "failure_reason", _normalize_text(self.failure_reason, "failure_reason"))
        object.__setattr__(self, "validation_message", _normalize_text(self.validation_message, "validation_message"))


@dataclass(frozen=True, slots=True)
class VisionOpeningContext:
    opening_location: VisionOpeningLocation
    opening_price: float
    cpr_relation: str
    camarilla_relation: str
    gap_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.opening_location, VisionOpeningLocation):
            raise TypeError("opening_location must be VisionOpeningLocation.")
        object.__setattr__(self, "opening_price", _positive_number(self.opening_price, "opening_price"))
        object.__setattr__(self, "cpr_relation", _normalize_text(self.cpr_relation, "cpr_relation"))
        object.__setattr__(self, "camarilla_relation", _normalize_text(self.camarilla_relation, "camarilla_relation"))
        object.__setattr__(self, "gap_type", _normalize_text(self.gap_type, "gap_type"))


@dataclass(frozen=True, slots=True)
class VisionPreviousDayContext:
    previous_high: float
    previous_low: float
    previous_close: float
    virgin_cpr: bool
    distance_previous_high: float
    distance_previous_low: float
    previous_day_relation: VisionPreviousDayRelation | None = None
    gap_type: VisionGapType | None = None

    def __post_init__(self) -> None:
        high = _positive_number(self.previous_high, "previous_high")
        low = _positive_number(self.previous_low, "previous_low")
        close = _positive_number(self.previous_close, "previous_close")
        if high < low:
            raise ValueError("previous_high cannot be below previous_low.")
        if close < low or close > high:
            raise ValueError("previous_close must be within the previous day range.")
        if not isinstance(self.virgin_cpr, bool):
            raise TypeError("virgin_cpr must be bool.")
        object.__setattr__(self, "previous_high", high)
        object.__setattr__(self, "previous_low", low)
        object.__setattr__(self, "previous_close", close)
        object.__setattr__(self, "distance_previous_high", _finite_number(self.distance_previous_high, "distance_previous_high"))
        object.__setattr__(self, "distance_previous_low", _finite_number(self.distance_previous_low, "distance_previous_low"))
        if self.previous_day_relation is not None and not isinstance(self.previous_day_relation, VisionPreviousDayRelation):
            raise TypeError("previous_day_relation must be VisionPreviousDayRelation or None.")
        if self.gap_type is not None and not isinstance(self.gap_type, VisionGapType):
            raise TypeError("gap_type must be VisionGapType or None.")


@dataclass(frozen=True, slots=True)
class VisionCPRContext:
    relation: VisionCPRRelation
    bc: float
    tc: float
    pivot: float
    width: float
    width_percentage: float

    def __post_init__(self) -> None:
        if not isinstance(self.relation, VisionCPRRelation):
            raise TypeError("relation must be VisionCPRRelation.")
        for field_name in ("bc", "tc", "pivot", "width", "width_percentage"):
            object.__setattr__(self, field_name, _finite_number(getattr(self, field_name), field_name))


@dataclass(frozen=True, slots=True)
class VisionCamarillaContext:
    zone: VisionCamarillaZone
    h3: float
    h4: float
    h5: float
    h6: float
    l3: float
    l4: float
    l5: float
    l6: float

    def __post_init__(self) -> None:
        if not isinstance(self.zone, VisionCamarillaZone):
            raise TypeError("zone must be VisionCamarillaZone.")
        for field_name in ("h3", "h4", "h5", "h6", "l3", "l4", "l5", "l6"):
            object.__setattr__(self, field_name, _finite_number(getattr(self, field_name), field_name))


@dataclass(frozen=True, slots=True)
class VisionADRContext:
    range_consumed_pct: float
    range_remaining_pct: float
    near_adr_resistance: bool
    near_adr_support: bool
    expansion: str
    exhaustion: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "range_consumed_pct", _finite_number(self.range_consumed_pct, "range_consumed_pct"))
        object.__setattr__(self, "range_remaining_pct", _finite_number(self.range_remaining_pct, "range_remaining_pct"))
        if not isinstance(self.near_adr_resistance, bool):
            raise TypeError("near_adr_resistance must be bool.")
        if not isinstance(self.near_adr_support, bool):
            raise TypeError("near_adr_support must be bool.")
        object.__setattr__(self, "expansion", _normalize_text(self.expansion, "expansion"))
        object.__setattr__(self, "exhaustion", _normalize_text(self.exhaustion, "exhaustion"))


@dataclass(frozen=True, slots=True)
class VisionVWAPContext:
    relation: VisionVWAPRelation
    vwap: float
    distance: float
    distance_pct: float

    def __post_init__(self) -> None:
        if not isinstance(self.relation, VisionVWAPRelation):
            raise TypeError("relation must be VisionVWAPRelation.")
        object.__setattr__(self, "vwap", _positive_number(self.vwap, "vwap"))
        object.__setattr__(self, "distance", _finite_number(self.distance, "distance"))
        object.__setattr__(self, "distance_pct", _finite_number(self.distance_pct, "distance_pct"))


@dataclass(frozen=True, slots=True)
class VisionOpeningRangeContext:
    opening_start_time: datetime
    opening_end_time: datetime
    opening_high: float
    opening_low: float
    opening_width: float
    range_complete: bool
    current_location: VisionRangeLocation
    break_direction: VisionBreakDirection
    retest_state: VisionOpeningRangeState
    false_break: bool
    elapsed_minutes: int
    quality: VisionLevelQuality
    expected_candle_count: int = 0
    actual_candle_count: int = 0
    missing_candle_timestamps: tuple[datetime, ...] = ()

    def __post_init__(self) -> None:
        _validate_aware(self.opening_start_time, "opening_start_time")
        _validate_aware(self.opening_end_time, "opening_end_time")
        if self.opening_end_time <= self.opening_start_time:
            raise ValueError("opening_end_time must be after opening_start_time.")
        high = _positive_number(self.opening_high, "opening_high")
        low = _positive_number(self.opening_low, "opening_low")
        if high < low:
            raise ValueError("opening_high cannot be below opening_low.")
        width = _finite_number(self.opening_width, "opening_width")
        if width != high - low:
            raise ValueError("opening_width must equal opening_high - opening_low.")
        if not isinstance(self.range_complete, bool):
            raise TypeError("range_complete must be bool.")
        if not isinstance(self.current_location, VisionRangeLocation):
            raise TypeError("current_location must be VisionRangeLocation.")
        if not isinstance(self.break_direction, VisionBreakDirection):
            raise TypeError("break_direction must be VisionBreakDirection.")
        if not isinstance(self.retest_state, VisionOpeningRangeState):
            raise TypeError("retest_state must be VisionOpeningRangeState.")
        if not isinstance(self.false_break, bool):
            raise TypeError("false_break must be bool.")
        if isinstance(self.elapsed_minutes, bool) or not isinstance(self.elapsed_minutes, int):
            raise TypeError("elapsed_minutes must be int.")
        if self.elapsed_minutes < 0:
            raise ValueError("elapsed_minutes cannot be negative.")
        if not isinstance(self.quality, VisionLevelQuality):
            raise TypeError("quality must be VisionLevelQuality.")
        if isinstance(self.expected_candle_count, bool) or not isinstance(self.expected_candle_count, int):
            raise TypeError("expected_candle_count must be int.")
        if self.expected_candle_count < 0:
            raise ValueError("expected_candle_count cannot be negative.")
        if isinstance(self.actual_candle_count, bool) or not isinstance(self.actual_candle_count, int):
            raise TypeError("actual_candle_count must be int.")
        if self.actual_candle_count < 0:
            raise ValueError("actual_candle_count cannot be negative.")
        missing = tuple(self.missing_candle_timestamps)
        for timestamp in missing:
            _validate_aware(timestamp, "missing_candle_timestamps")
        object.__setattr__(self, "missing_candle_timestamps", missing)
        object.__setattr__(self, "opening_high", high)
        object.__setattr__(self, "opening_low", low)


@dataclass(frozen=True, slots=True)
class VisionSwingPoint:
    price: float
    time: datetime
    index: int
    strength: int
    type: VisionSwingType

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", _positive_number(self.price, "price"))
        _validate_aware(self.time, "time")
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise TypeError("index must be int.")
        if self.index < 0:
            raise ValueError("index cannot be negative.")
        if isinstance(self.strength, bool) or not isinstance(self.strength, int):
            raise TypeError("strength must be int.")
        if self.strength <= 0:
            raise ValueError("strength must be positive.")
        if not isinstance(self.type, VisionSwingType):
            raise TypeError("type must be VisionSwingType.")


@dataclass(frozen=True, slots=True)
class VisionStructureContext:
    current_swing_high: VisionSwingPoint | None
    current_swing_low: VisionSwingPoint | None
    previous_swing_high: VisionSwingPoint | None
    previous_swing_low: VisionSwingPoint | None
    trend: VisionStructureTrend
    structure_state: VisionStructurePattern
    last_confirmed_swing: VisionSwingPoint | None
    quality: VisionLevelQuality

    def __post_init__(self) -> None:
        for field_name in (
            "current_swing_high",
            "current_swing_low",
            "previous_swing_high",
            "previous_swing_low",
            "last_confirmed_swing",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, VisionSwingPoint):
                raise TypeError(f"{field_name} must be VisionSwingPoint or None.")
        if not isinstance(self.trend, VisionStructureTrend):
            raise TypeError("trend must be VisionStructureTrend.")
        if not isinstance(self.structure_state, VisionStructurePattern):
            raise TypeError("structure_state must be VisionStructurePattern.")
        if not isinstance(self.quality, VisionLevelQuality):
            raise TypeError("quality must be VisionLevelQuality.")


@dataclass(frozen=True, slots=True)
class VisionLiquidityLevel:
    price: float
    start_time: datetime
    end_time: datetime
    indexes: tuple[int, ...]
    type: VisionSwingType
    tolerance_pct: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", _positive_number(self.price, "price"))
        _validate_aware(self.start_time, "start_time")
        _validate_aware(self.end_time, "end_time")
        if self.end_time < self.start_time:
            raise ValueError("end_time cannot be before start_time.")
        object.__setattr__(self, "indexes", _normalize_index_tuple(self.indexes, "indexes"))
        if len(self.indexes) < 2:
            raise ValueError("liquidity level requires at least two indexes.")
        if not isinstance(self.type, VisionSwingType):
            raise TypeError("type must be VisionSwingType.")
        tolerance = _finite_number(self.tolerance_pct, "tolerance_pct")
        if tolerance < 0:
            raise ValueError("tolerance_pct cannot be negative.")
        object.__setattr__(self, "tolerance_pct", tolerance)


@dataclass(frozen=True, slots=True)
class VisionFairValueGap:
    direction: VisionFairValueGapDirection
    start_time: datetime
    end_time: datetime
    lower_bound: float
    upper_bound: float
    candle_indexes: tuple[int, int, int]

    def __post_init__(self) -> None:
        if not isinstance(self.direction, VisionFairValueGapDirection):
            raise TypeError("direction must be VisionFairValueGapDirection.")
        if self.direction is VisionFairValueGapDirection.NONE:
            raise ValueError("fair value gap direction cannot be NONE.")
        _validate_aware(self.start_time, "start_time")
        _validate_aware(self.end_time, "end_time")
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time.")
        lower = _positive_number(self.lower_bound, "lower_bound")
        upper = _positive_number(self.upper_bound, "upper_bound")
        if upper <= lower:
            raise ValueError("upper_bound must be above lower_bound.")
        if not isinstance(self.candle_indexes, tuple) or len(self.candle_indexes) != 3:
            raise TypeError("candle_indexes must be a three-item tuple.")
        object.__setattr__(self, "candle_indexes", _normalize_index_tuple(self.candle_indexes, "candle_indexes"))
        object.__setattr__(self, "lower_bound", lower)
        object.__setattr__(self, "upper_bound", upper)


@dataclass(frozen=True, slots=True)
class VisionOrderBlock:
    direction: VisionOrderBlockDirection
    candle_index: int
    start_time: datetime
    end_time: datetime
    high: float
    low: float

    def __post_init__(self) -> None:
        if not isinstance(self.direction, VisionOrderBlockDirection):
            raise TypeError("direction must be VisionOrderBlockDirection.")
        if self.direction is VisionOrderBlockDirection.NONE:
            raise ValueError("order block direction cannot be NONE.")
        if isinstance(self.candle_index, bool) or not isinstance(self.candle_index, int):
            raise TypeError("candle_index must be int.")
        if self.candle_index < 0:
            raise ValueError("candle_index cannot be negative.")
        _validate_aware(self.start_time, "start_time")
        _validate_aware(self.end_time, "end_time")
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time.")
        high = _positive_number(self.high, "high")
        low = _positive_number(self.low, "low")
        if high < low:
            raise ValueError("high cannot be below low.")
        object.__setattr__(self, "high", high)
        object.__setattr__(self, "low", low)


@dataclass(frozen=True, slots=True)
class VisionBreakerBlock:
    state: VisionBreakerBlockState = VisionBreakerBlockState.NOT_EVALUATED

    def __post_init__(self) -> None:
        if not isinstance(self.state, VisionBreakerBlockState):
            raise TypeError("state must be VisionBreakerBlockState.")


@dataclass(frozen=True, slots=True)
class VisionLiquidityContext:
    equal_highs: tuple[VisionLiquidityLevel, ...]
    equal_lows: tuple[VisionLiquidityLevel, ...]
    liquidity_pool: VisionLiquidityPool
    liquidity_sweep: VisionLiquiditySweep
    sweep_direction: VisionSweepDirection
    fair_value_gap: VisionFairValueGap | None
    order_block: VisionOrderBlock | None
    breaker_block: VisionBreakerBlock
    mitigation: VisionMitigationState
    quality: VisionLevelQuality

    def __post_init__(self) -> None:
        object.__setattr__(self, "equal_highs", _normalize_liquidity_levels(self.equal_highs, "equal_highs"))
        object.__setattr__(self, "equal_lows", _normalize_liquidity_levels(self.equal_lows, "equal_lows"))
        if not isinstance(self.liquidity_pool, VisionLiquidityPool):
            raise TypeError("liquidity_pool must be VisionLiquidityPool.")
        if not isinstance(self.liquidity_sweep, VisionLiquiditySweep):
            raise TypeError("liquidity_sweep must be VisionLiquiditySweep.")
        if not isinstance(self.sweep_direction, VisionSweepDirection):
            raise TypeError("sweep_direction must be VisionSweepDirection.")
        if self.fair_value_gap is not None and not isinstance(self.fair_value_gap, VisionFairValueGap):
            raise TypeError("fair_value_gap must be VisionFairValueGap or None.")
        if self.order_block is not None and not isinstance(self.order_block, VisionOrderBlock):
            raise TypeError("order_block must be VisionOrderBlock or None.")
        if not isinstance(self.breaker_block, VisionBreakerBlock):
            raise TypeError("breaker_block must be VisionBreakerBlock.")
        if not isinstance(self.mitigation, VisionMitigationState):
            raise TypeError("mitigation must be VisionMitigationState.")
        if not isinstance(self.quality, VisionLevelQuality):
            raise TypeError("quality must be VisionLevelQuality.")
        if self.liquidity_pool is VisionLiquidityPool.NONE and (
            self.liquidity_sweep is not VisionLiquiditySweep.NONE or self.sweep_direction is not VisionSweepDirection.NONE
        ):
            raise ValueError("sweeps require an identified liquidity pool.")
        if self.liquidity_sweep is VisionLiquiditySweep.NONE and self.sweep_direction is not VisionSweepDirection.NONE:
            raise ValueError("sweep_direction must be NONE when no liquidity sweep exists.")


@dataclass(frozen=True, slots=True)
class VisionStructureEventContext:
    bos: VisionBOS
    choch: VisionCHoCH
    mss: VisionMSS
    continuation: VisionStructureEventPhase
    reversal: VisionReversalState
    break_strength: VisionBreakStrength
    quality: VisionLevelQuality

    def __post_init__(self) -> None:
        if not isinstance(self.bos, VisionBOS):
            raise TypeError("bos must be VisionBOS.")
        if not isinstance(self.choch, VisionCHoCH):
            raise TypeError("choch must be VisionCHoCH.")
        if not isinstance(self.mss, VisionMSS):
            raise TypeError("mss must be VisionMSS.")
        if not isinstance(self.continuation, VisionStructureEventPhase):
            raise TypeError("continuation must be VisionStructureEventPhase.")
        if not isinstance(self.reversal, VisionReversalState):
            raise TypeError("reversal must be VisionReversalState.")
        if not isinstance(self.break_strength, VisionBreakStrength):
            raise TypeError("break_strength must be VisionBreakStrength.")
        if not isinstance(self.quality, VisionLevelQuality):
            raise TypeError("quality must be VisionLevelQuality.")
        if self.bos is not VisionBOS.NONE and self.choch is not VisionCHoCH.NONE:
            raise ValueError("BOS and CHoCH cannot both be active.")
        if self.bos is not VisionBOS.NONE and self.continuation is not VisionStructureEventPhase.CONTINUATION:
            raise ValueError("BOS requires continuation state.")
        if self.choch is not VisionCHoCH.NONE and self.continuation is not VisionStructureEventPhase.REVERSAL:
            raise ValueError("CHoCH requires reversal state.")
        if self.choch is VisionCHoCH.BULLISH_CHOCH and self.reversal is not VisionReversalState.BULLISH_REVERSAL:
            raise ValueError("bullish CHoCH requires bullish reversal.")
        if self.choch is VisionCHoCH.BEARISH_CHOCH and self.reversal is not VisionReversalState.BEARISH_REVERSAL:
            raise ValueError("bearish CHoCH requires bearish reversal.")
        if self.choch is VisionCHoCH.NONE and self.reversal is not VisionReversalState.NONE:
            raise ValueError("reversal requires CHoCH.")
        if self.mss is VisionMSS.MARKET_STRUCTURE_SHIFT and self.choch is VisionCHoCH.NONE:
            raise ValueError("MSS requires CHoCH.")
        if (
            self.bos is VisionBOS.NONE
            and self.choch is VisionCHoCH.NONE
            and self.break_strength is not VisionBreakStrength.NONE
        ):
            raise ValueError("break strength requires a structure event.")


@dataclass(frozen=True, slots=True)
class VisionSetupQualificationContext:
    setup_type: VisionSetupType
    setup_quality: VisionSetupQuality
    blocking_reasons: tuple[str, ...]
    supporting_reasons: tuple[str, ...]
    eligible_for_option_confirmation: bool

    def __post_init__(self) -> None:
        if not isinstance(self.setup_type, VisionSetupType):
            raise TypeError("setup_type must be VisionSetupType.")
        if not isinstance(self.setup_quality, VisionSetupQuality):
            raise TypeError("setup_quality must be VisionSetupQuality.")
        blocking = _normalize_unique_text_tuple(self.blocking_reasons, "blocking_reasons")
        supporting = _normalize_unique_text_tuple(self.supporting_reasons, "supporting_reasons")
        if not isinstance(self.eligible_for_option_confirmation, bool):
            raise TypeError("eligible_for_option_confirmation must be bool.")
        if self.setup_type is VisionSetupType.NO_QUALITY_SETUP and self.eligible_for_option_confirmation:
            raise ValueError("no quality setup cannot be eligible for option confirmation.")
        if self.setup_quality is VisionSetupQuality.INVALID and self.eligible_for_option_confirmation:
            raise ValueError("invalid setup cannot be eligible for option confirmation.")
        if self.setup_quality is VisionSetupQuality.INVALID and not blocking:
            raise ValueError("invalid setup requires blocking reasons.")
        if self.eligible_for_option_confirmation and blocking:
            raise ValueError("eligible setup cannot have blocking reasons.")
        object.__setattr__(self, "blocking_reasons", blocking)
        object.__setattr__(self, "supporting_reasons", supporting)


@dataclass(frozen=True, slots=True)
class VisionOptionConfirmationContext:
    confirmation_state: VisionOptionConfirmation
    supporting_factors: tuple[str, ...]
    contradicting_factors: tuple[str, ...]
    neutral_factors: tuple[str, ...]
    quality: VisionLevelQuality
    timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.confirmation_state, VisionOptionConfirmation):
            raise TypeError("confirmation_state must be VisionOptionConfirmation.")
        supporting = _normalize_unique_text_tuple(self.supporting_factors, "supporting_factors")
        contradicting = _normalize_unique_text_tuple(self.contradicting_factors, "contradicting_factors")
        neutral = _normalize_unique_text_tuple(self.neutral_factors, "neutral_factors")
        _validate_unique_factor_groups(supporting, contradicting, neutral)
        if not isinstance(self.quality, VisionLevelQuality):
            raise TypeError("quality must be VisionLevelQuality.")
        _validate_aware(self.timestamp, "timestamp")
        if self.confirmation_state is VisionOptionConfirmation.CONFIRMS and not supporting:
            raise ValueError("confirming option context requires supporting factors.")
        if self.confirmation_state is VisionOptionConfirmation.CONTRADICTS and not contradicting:
            raise ValueError("contradicting option context requires contradicting factors.")
        if self.confirmation_state is VisionOptionConfirmation.PARTIAL and (not supporting or not contradicting):
            raise ValueError("partial option context requires supporting and contradicting factors.")
        if self.confirmation_state is VisionOptionConfirmation.NEUTRAL and not neutral:
            raise ValueError("neutral option context requires neutral factors.")
        if self.confirmation_state is VisionOptionConfirmation.UNAVAILABLE and self.quality is not VisionLevelQuality.INSUFFICIENT:
            raise ValueError("unavailable option context requires insufficient quality.")
        object.__setattr__(self, "supporting_factors", supporting)
        object.__setattr__(self, "contradicting_factors", contradicting)
        object.__setattr__(self, "neutral_factors", neutral)


@dataclass(frozen=True, slots=True)
class VisionEntryLocationContext:
    direction: str
    direction_quality: VisionDirectionQuality
    entry_location_state: VisionEntryLocationState
    entry_location_quality: VisionLevelQuality
    remaining_room: float | None
    nearest_target_or_destination: str
    nearest_invalidation: str
    move_maturity: VisionMoveMaturity
    retest_state: str
    chase_risk: VisionChaseRisk
    location_supporting_reasons: tuple[str, ...]
    location_warning_reasons: tuple[str, ...]
    location_blocking_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        direction = _normalize_text(self.direction, "direction").casefold()
        if direction not in {"bullish", "bearish", "neutral", "unknown"}:
            raise ValueError("direction must be bullish, bearish, neutral, or unknown.")
        object.__setattr__(self, "direction", direction)
        if not isinstance(self.direction_quality, VisionDirectionQuality):
            raise TypeError("direction_quality must be VisionDirectionQuality.")
        if not isinstance(self.entry_location_state, VisionEntryLocationState):
            raise TypeError("entry_location_state must be VisionEntryLocationState.")
        if not isinstance(self.entry_location_quality, VisionLevelQuality):
            raise TypeError("entry_location_quality must be VisionLevelQuality.")
        if self.remaining_room is not None:
            room = _finite_number(self.remaining_room, "remaining_room")
            if room < 0:
                raise ValueError("remaining_room cannot be negative.")
            object.__setattr__(self, "remaining_room", room)
        object.__setattr__(self, "nearest_target_or_destination", _normalize_text(self.nearest_target_or_destination, "nearest_target_or_destination"))
        object.__setattr__(self, "nearest_invalidation", _normalize_text(self.nearest_invalidation, "nearest_invalidation"))
        if not isinstance(self.move_maturity, VisionMoveMaturity):
            raise TypeError("move_maturity must be VisionMoveMaturity.")
        object.__setattr__(self, "retest_state", _normalize_text(self.retest_state, "retest_state"))
        if not isinstance(self.chase_risk, VisionChaseRisk):
            raise TypeError("chase_risk must be VisionChaseRisk.")
        object.__setattr__(self, "location_supporting_reasons", _normalize_unique_text_tuple(self.location_supporting_reasons, "location_supporting_reasons"))
        object.__setattr__(self, "location_warning_reasons", _normalize_unique_text_tuple(self.location_warning_reasons, "location_warning_reasons"))
        object.__setattr__(self, "location_blocking_reasons", _normalize_unique_text_tuple(self.location_blocking_reasons, "location_blocking_reasons"))


@dataclass(frozen=True, slots=True)
class VisionLevelContext:
    cpr_context: VisionCPRContext
    camarilla_context: VisionCamarillaContext
    previous_day_context: VisionPreviousDayContext
    adr_context: VisionADRContext | None
    vwap_context: VisionVWAPContext | None
    quality: VisionLevelQuality
    missing_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.cpr_context, VisionCPRContext):
            raise TypeError("cpr_context must be VisionCPRContext.")
        if not isinstance(self.camarilla_context, VisionCamarillaContext):
            raise TypeError("camarilla_context must be VisionCamarillaContext.")
        if not isinstance(self.previous_day_context, VisionPreviousDayContext):
            raise TypeError("previous_day_context must be VisionPreviousDayContext.")
        if self.adr_context is not None and not isinstance(self.adr_context, VisionADRContext):
            raise TypeError("adr_context must be VisionADRContext or None.")
        if self.vwap_context is not None and not isinstance(self.vwap_context, VisionVWAPContext):
            raise TypeError("vwap_context must be VisionVWAPContext or None.")
        if not isinstance(self.quality, VisionLevelQuality):
            raise TypeError("quality must be VisionLevelQuality.")
        object.__setattr__(self, "missing_evidence", _normalize_text_tuple(self.missing_evidence, "missing_evidence"))


@dataclass(frozen=True, slots=True)
class VisionMethodSnapshot:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    timestamp: datetime
    opening_context: VisionOpeningContext
    previous_day_context: VisionPreviousDayContext
    level_context: VisionLevelContext
    opening_range_context: VisionOpeningRangeContext
    structure_context: VisionStructureContext
    liquidity_context: VisionLiquidityContext
    structure_event_context: VisionStructureEventContext
    setup_qualification_context: VisionSetupQualificationContext
    option_confirmation_context: VisionOptionConfirmationContext
    market_regime: VisionMarketRegime
    candidate_state: VisionCandidateState
    blocking_reasons: tuple[str, ...]
    supporting_reasons: tuple[str, ...]
    quality: str
    pivot_flight_plan: VisionPivotFlightPlan | None = None
    pivot_opening_assessment: "VisionPivotOpeningAssessment | None" = None
    pivot_confluence_context: "VisionPivotConfluenceContext | None" = None
    entry_location_context: VisionEntryLocationContext = field(default_factory=lambda: VisionEntryLocationContext(
        direction="unknown",
        direction_quality=VisionDirectionQuality.INVALID,
        entry_location_state=VisionEntryLocationState.INSUFFICIENT_DATA,
        entry_location_quality=VisionLevelQuality.INSUFFICIENT,
        remaining_room=None,
        nearest_target_or_destination="unknown",
        nearest_invalidation="unknown",
        move_maturity=VisionMoveMaturity.UNKNOWN,
        retest_state="unknown",
        chase_risk=VisionChaseRisk.HIGH,
        location_supporting_reasons=(),
        location_warning_reasons=("Entry location not evaluated",),
        location_blocking_reasons=("Entry location unavailable",),
    ))
    assembly_failures: tuple[VisionContextAssemblyFailure, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        _validate_aware(self.timestamp, "timestamp")
        if not isinstance(self.opening_context, VisionOpeningContext):
            raise TypeError("opening_context must be VisionOpeningContext.")
        if not isinstance(self.previous_day_context, VisionPreviousDayContext):
            raise TypeError("previous_day_context must be VisionPreviousDayContext.")
        if not isinstance(self.level_context, VisionLevelContext):
            raise TypeError("level_context must be VisionLevelContext.")
        if not isinstance(self.opening_range_context, VisionOpeningRangeContext):
            raise TypeError("opening_range_context must be VisionOpeningRangeContext.")
        if not isinstance(self.structure_context, VisionStructureContext):
            raise TypeError("structure_context must be VisionStructureContext.")
        if not isinstance(self.liquidity_context, VisionLiquidityContext):
            raise TypeError("liquidity_context must be VisionLiquidityContext.")
        if not isinstance(self.structure_event_context, VisionStructureEventContext):
            raise TypeError("structure_event_context must be VisionStructureEventContext.")
        if not isinstance(self.setup_qualification_context, VisionSetupQualificationContext):
            raise TypeError("setup_qualification_context must be VisionSetupQualificationContext.")
        if not isinstance(self.option_confirmation_context, VisionOptionConfirmationContext):
            raise TypeError("option_confirmation_context must be VisionOptionConfirmationContext.")
        if not isinstance(self.market_regime, VisionMarketRegime):
            raise TypeError("market_regime must be VisionMarketRegime.")
        if not isinstance(self.candidate_state, VisionCandidateState):
            raise TypeError("candidate_state must be VisionCandidateState.")
        if not isinstance(self.entry_location_context, VisionEntryLocationContext):
            raise TypeError("entry_location_context must be VisionEntryLocationContext.")
        if self.pivot_flight_plan is not None:
            if not isinstance(self.pivot_flight_plan, VisionPivotFlightPlan):
                raise TypeError("pivot_flight_plan must be VisionPivotFlightPlan or None.")
            if self.pivot_flight_plan.instrument is not self.instrument:
                raise ValueError("pivot_flight_plan instrument mismatch.")
            if self.pivot_flight_plan.trading_date != self.timestamp.date():
                raise ValueError("pivot_flight_plan trading date mismatch.")
        if self.pivot_opening_assessment is not None:
            from .opening_assessment import VisionPivotOpeningAssessment

            if not isinstance(self.pivot_opening_assessment, VisionPivotOpeningAssessment):
                raise TypeError("pivot_opening_assessment must be VisionPivotOpeningAssessment or None.")
            if self.pivot_opening_assessment.instrument is not self.instrument:
                raise ValueError("pivot_opening_assessment instrument mismatch.")
            if self.pivot_opening_assessment.trading_date != self.timestamp.date():
                raise ValueError("pivot_opening_assessment trading date mismatch.")
        if self.pivot_confluence_context is not None:
            from .pivot_confluence import VisionPivotConfluenceContext

            if not isinstance(self.pivot_confluence_context, VisionPivotConfluenceContext):
                raise TypeError("pivot_confluence_context must be VisionPivotConfluenceContext or None.")
            if self.pivot_confluence_context.instrument is not self.instrument:
                raise ValueError("pivot_confluence_context instrument mismatch.")
            if self.pivot_confluence_context.timeframe is not self.timeframe:
                raise ValueError("pivot_confluence_context timeframe mismatch.")
            if self.pivot_confluence_context.trading_date != self.timestamp.date():
                raise ValueError("pivot_confluence_context trading date mismatch.")
            if self.pivot_confluence_context.timestamp > self.timestamp:
                raise ValueError("pivot_confluence_context timestamp cannot be after snapshot timestamp.")
        object.__setattr__(self, "blocking_reasons", _normalize_text_tuple(self.blocking_reasons, "blocking_reasons"))
        object.__setattr__(self, "supporting_reasons", _normalize_text_tuple(self.supporting_reasons, "supporting_reasons"))
        object.__setattr__(self, "quality", _normalize_text(self.quality, "quality"))
        object.__setattr__(self, "assembly_failures", _normalize_assembly_failures(self.assembly_failures))


def _normalize_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple.")
    return tuple(_normalize_text(item, field_name) for item in values)


def _normalize_unique_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = _normalize_text_tuple(values, field_name)
    lowered: set[str] = set()
    for item in normalized:
        key = item.casefold()
        if key in lowered:
            raise ValueError(f"{field_name} cannot contain duplicate reasons.")
        lowered.add(key)
    return normalized


def _validate_unique_factor_groups(*groups: tuple[str, ...]) -> None:
    seen: set[str] = set()
    for group in groups:
        for item in group:
            key = item.casefold()
            if key in seen:
                raise ValueError("option confirmation factors cannot be duplicated.")
            seen.add(key)


def _normalize_index_tuple(values: tuple[int, ...], field_name: str) -> tuple[int, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple.")
    normalized: list[int] = []
    previous: int | None = None
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{field_name} must contain integers.")
        if value < 0:
            raise ValueError(f"{field_name} cannot contain negative indexes.")
        if previous is not None and value <= previous:
            raise ValueError(f"{field_name} must be strictly increasing.")
        normalized.append(value)
        previous = value
    return tuple(normalized)


def _normalize_liquidity_levels(values: tuple[VisionLiquidityLevel, ...], field_name: str) -> tuple[VisionLiquidityLevel, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple.")
    normalized: list[VisionLiquidityLevel] = []
    identities: set[tuple[VisionSwingType, tuple[int, ...]]] = set()
    for value in values:
        if not isinstance(value, VisionLiquidityLevel):
            raise TypeError(f"{field_name} must contain VisionLiquidityLevel objects.")
        identity = (value.type, value.indexes)
        if identity in identities:
            raise ValueError("duplicate liquidity pool.")
        identities.add(identity)
        normalized.append(value)
    return tuple(normalized)


def _normalize_assembly_failures(values: tuple[VisionContextAssemblyFailure, ...]) -> tuple[VisionContextAssemblyFailure, ...]:
    if not isinstance(values, tuple):
        raise TypeError("assembly_failures must be a tuple.")
    normalized: list[VisionContextAssemblyFailure] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, VisionContextAssemblyFailure):
            raise TypeError("assembly_failures must contain VisionContextAssemblyFailure objects.")
        key = value.stage.casefold()
        if key in seen:
            raise ValueError("assembly_failures cannot contain duplicate stages.")
        seen.add(key)
        normalized.append(value)
    return tuple(normalized)


def _normalize_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text.")
    return value.strip()


def _finite_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric.")
    normalized = float(value)
    if normalized != normalized or normalized in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} must be finite.")
    return normalized


def _positive_number(value: float, field_name: str) -> float:
    normalized = _finite_number(value, field_name)
    if normalized <= 0:
        raise ValueError(f"{field_name} must be positive.")
    return normalized


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
