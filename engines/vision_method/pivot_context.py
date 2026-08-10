"""
Pre-market pivot context and flight-plan intelligence.

VPM_CONTEXT_1 consumes canonical CPR/Camarilla levels plus historical daily
context. It does not recalculate live indicators, generate entries, or create
trade candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from statistics import median

from application.enums import RuntimeInstrument
from core.models.daily_ohlc import DailyOHLC
from engines.camarilla.calculator import CamarillaCalculator
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.calculator import CPRCalculator
from engines.cpr.levels import CPRLevels

from .enums import (
    VisionPivotCombinedContext,
    VisionPivotDirectionalPrior,
    VisionPivotRelationship,
    VisionPivotTendency,
    VisionPivotWidthState,
    VisionScenarioStatus,
)


@dataclass(frozen=True, slots=True)
class VisionPivotContextConfiguration:
    pivot_width_history_sessions: int = 5
    narrow_width_ratio: float = 0.75
    wide_width_ratio: float = 1.25
    unchanged_relationship_tolerance: float = 0.05

    def __post_init__(self) -> None:
        if isinstance(self.pivot_width_history_sessions, bool) or not isinstance(self.pivot_width_history_sessions, int):
            raise TypeError("pivot_width_history_sessions must be int.")
        if self.pivot_width_history_sessions < 2:
            raise ValueError("pivot_width_history_sessions must be at least 2.")
        for field_name in ("narrow_width_ratio", "wide_width_ratio", "unchanged_relationship_tolerance"):
            value = _finite_number(getattr(self, field_name), field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive.")
            object.__setattr__(self, field_name, value)
        if self.narrow_width_ratio >= self.wide_width_ratio:
            raise ValueError("narrow_width_ratio must be below wide_width_ratio.")


@dataclass(frozen=True, slots=True)
class VisionPivotActionZone:
    label: str
    condition: str
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _normalize_text(self.label, "label"))
        object.__setattr__(self, "condition", _normalize_text(self.condition, "condition"))
        object.__setattr__(self, "source", _normalize_text(self.source, "source"))


@dataclass(frozen=True, slots=True)
class VisionPivotFlightPlan:
    instrument: RuntimeInstrument
    trading_date: date
    reference_session_date: date
    generated_at: datetime
    cpr_relationship: VisionPivotRelationship
    cpr_width_state: VisionPivotWidthState
    cpr_width_value: float
    cpr_directional_prior: VisionPivotDirectionalPrior
    camarilla_relationship: VisionPivotRelationship
    camarilla_width_state: VisionPivotWidthState
    camarilla_width_value: float
    camarilla_directional_prior: VisionPivotDirectionalPrior
    combined_context_state: VisionPivotCombinedContext
    combined_directional_prior: VisionPivotDirectionalPrior
    expansion_tendency: VisionPivotTendency
    balance_tendency: VisionPivotTendency
    preferred_bullish_action_zones: tuple[VisionPivotActionZone, ...]
    preferred_bearish_action_zones: tuple[VisionPivotActionZone, ...]
    bullish_scenario: str
    bearish_scenario: str
    neutral_or_breakout_scenario: str
    scenario_status: VisionScenarioStatus
    opening_confirmation_required: bool
    supporting_reasons: tuple[str, ...]
    conflicting_reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        for field_name in ("trading_date", "reference_session_date"):
            value = getattr(self, field_name)
            if not isinstance(value, date) or isinstance(value, datetime):
                raise TypeError(f"{field_name} must be date.")
        if self.reference_session_date >= self.trading_date:
            raise ValueError("reference_session_date must be before trading_date.")
        _validate_aware(self.generated_at, "generated_at")
        _require_enum(self.cpr_relationship, VisionPivotRelationship, "cpr_relationship")
        _require_enum(self.cpr_width_state, VisionPivotWidthState, "cpr_width_state")
        _require_enum(self.cpr_directional_prior, VisionPivotDirectionalPrior, "cpr_directional_prior")
        _require_enum(self.camarilla_relationship, VisionPivotRelationship, "camarilla_relationship")
        _require_enum(self.camarilla_width_state, VisionPivotWidthState, "camarilla_width_state")
        _require_enum(self.camarilla_directional_prior, VisionPivotDirectionalPrior, "camarilla_directional_prior")
        _require_enum(self.combined_context_state, VisionPivotCombinedContext, "combined_context_state")
        _require_enum(self.combined_directional_prior, VisionPivotDirectionalPrior, "combined_directional_prior")
        _require_enum(self.expansion_tendency, VisionPivotTendency, "expansion_tendency")
        _require_enum(self.balance_tendency, VisionPivotTendency, "balance_tendency")
        _require_enum(self.scenario_status, VisionScenarioStatus, "scenario_status")
        object.__setattr__(self, "cpr_width_value", _finite_number(self.cpr_width_value, "cpr_width_value"))
        object.__setattr__(self, "camarilla_width_value", _finite_number(self.camarilla_width_value, "camarilla_width_value"))
        if not isinstance(self.opening_confirmation_required, bool):
            raise TypeError("opening_confirmation_required must be bool.")
        if not self.opening_confirmation_required:
            raise ValueError("pivot flight plan must require opening confirmation in VPM_CONTEXT_1.")
        object.__setattr__(self, "preferred_bullish_action_zones", _normalize_zones(self.preferred_bullish_action_zones, "preferred_bullish_action_zones"))
        object.__setattr__(self, "preferred_bearish_action_zones", _normalize_zones(self.preferred_bearish_action_zones, "preferred_bearish_action_zones"))
        for field_name in ("bullish_scenario", "bearish_scenario", "neutral_or_breakout_scenario"):
            object.__setattr__(self, field_name, _normalize_text(getattr(self, field_name), field_name))
        object.__setattr__(self, "supporting_reasons", _normalize_unique_text_tuple(self.supporting_reasons, "supporting_reasons"))
        object.__setattr__(self, "conflicting_reasons", _normalize_unique_text_tuple(self.conflicting_reasons, "conflicting_reasons"))
        object.__setattr__(self, "warnings", _normalize_unique_text_tuple(self.warnings, "warnings"))


@dataclass(frozen=True, slots=True)
class VisionPivotFlightPlanRequest:
    instrument: RuntimeInstrument
    trading_date: date
    reference_session_date: date
    generated_at: datetime
    current_cpr: CPRLevels
    current_camarilla: CamarillaLevels
    historical_daily_ohlc: tuple[DailyOHLC, ...]
    configuration: VisionPivotContextConfiguration = field(default_factory=VisionPivotContextConfiguration)

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        for field_name in ("trading_date", "reference_session_date"):
            value = getattr(self, field_name)
            if not isinstance(value, date) or isinstance(value, datetime):
                raise TypeError(f"{field_name} must be date.")
        if self.reference_session_date >= self.trading_date:
            raise ValueError("reference_session_date must be before trading_date.")
        _validate_aware(self.generated_at, "generated_at")
        if not isinstance(self.current_cpr, CPRLevels):
            raise TypeError("current_cpr must be CPRLevels.")
        if not isinstance(self.current_camarilla, CamarillaLevels):
            raise TypeError("current_camarilla must be CamarillaLevels.")
        if not isinstance(self.historical_daily_ohlc, tuple):
            raise TypeError("historical_daily_ohlc must be tuple.")
        for item in self.historical_daily_ohlc:
            if not isinstance(item, DailyOHLC):
                raise TypeError("historical_daily_ohlc must contain DailyOHLC values.")
        if not isinstance(self.configuration, VisionPivotContextConfiguration):
            raise TypeError("configuration must be VisionPivotContextConfiguration.")


def build_pivot_flight_plan(request: VisionPivotFlightPlanRequest) -> VisionPivotFlightPlan:
    validate_pivot_flight_plan_request(request)
    previous_daily = _previous_daily_for_reference(request.historical_daily_ohlc, request.reference_session_date)
    cpr_relationship = VisionPivotRelationship.INSUFFICIENT_DATA
    camarilla_relationship = VisionPivotRelationship.INSUFFICIENT_DATA
    warnings: list[str] = []

    if previous_daily is None:
        warnings.append("Previous completed pivot reference is unavailable")
    else:
        prior_cpr = CPRCalculator.calculate(previous_daily)
        prior_camarilla = CamarillaCalculator.calculate(previous_daily)
        cpr_relationship = classify_pivot_relationship(
            _cpr_range(request.current_cpr),
            _cpr_range(prior_cpr),
            tolerance=request.configuration.unchanged_relationship_tolerance,
        )
        camarilla_relationship = classify_pivot_relationship(
            _camarilla_h3_l3_range(request.current_camarilla),
            _camarilla_h3_l3_range(prior_camarilla),
            tolerance=request.configuration.unchanged_relationship_tolerance,
        )

    cpr_width_sample = _historical_cpr_widths(request.historical_daily_ohlc, request.reference_session_date)
    camarilla_width_sample = _historical_camarilla_widths(request.historical_daily_ohlc, request.reference_session_date)
    cpr_width_state = classify_width(
        request.current_cpr.width,
        cpr_width_sample,
        configuration=request.configuration,
    )
    camarilla_width = abs(request.current_camarilla.h3 - request.current_camarilla.l3)
    camarilla_width_state = classify_width(
        camarilla_width,
        camarilla_width_sample,
        configuration=request.configuration,
    )
    if cpr_width_state is VisionPivotWidthState.INSUFFICIENT_DATA:
        warnings.append("Insufficient CPR width history")
    if camarilla_width_state is VisionPivotWidthState.INSUFFICIENT_DATA:
        warnings.append("Insufficient Camarilla width history")

    cpr_prior = _directional_prior(cpr_relationship)
    camarilla_prior = _directional_prior(camarilla_relationship)
    combined_context, combined_prior, conflicts = _combined_context(
        cpr_relationship,
        cpr_width_state,
        cpr_prior,
        camarilla_relationship,
        camarilla_width_state,
        camarilla_prior,
    )
    expansion = _expansion_tendency(combined_context, cpr_width_state, camarilla_width_state)
    balance = _balance_tendency(combined_context, cpr_width_state, camarilla_width_state)
    supporting = _supporting_reasons(
        cpr_relationship,
        cpr_width_state,
        cpr_prior,
        camarilla_relationship,
        camarilla_width_state,
        camarilla_prior,
        combined_context,
        expansion,
        balance,
    )

    return VisionPivotFlightPlan(
        instrument=request.instrument,
        trading_date=request.trading_date,
        reference_session_date=request.reference_session_date,
        generated_at=request.generated_at,
        cpr_relationship=cpr_relationship,
        cpr_width_state=cpr_width_state,
        cpr_width_value=request.current_cpr.width,
        cpr_directional_prior=cpr_prior,
        camarilla_relationship=camarilla_relationship,
        camarilla_width_state=camarilla_width_state,
        camarilla_width_value=camarilla_width,
        camarilla_directional_prior=camarilla_prior,
        combined_context_state=combined_context,
        combined_directional_prior=combined_prior,
        expansion_tendency=expansion,
        balance_tendency=balance,
        preferred_bullish_action_zones=_bullish_zones(camarilla_relationship, combined_context),
        preferred_bearish_action_zones=_bearish_zones(camarilla_relationship, combined_context),
        bullish_scenario="Bullish scenario remains provisional until the opening print confirms value acceptance.",
        bearish_scenario="Bearish scenario remains provisional until the opening print confirms value acceptance.",
        neutral_or_breakout_scenario=_neutral_scenario(combined_context),
        scenario_status=VisionScenarioStatus.OPENING_CONFIRMATION_REQUIRED,
        opening_confirmation_required=True,
        supporting_reasons=supporting,
        conflicting_reasons=tuple(conflicts),
        warnings=tuple(warnings),
    )


def validate_pivot_flight_plan_request(request: VisionPivotFlightPlanRequest) -> VisionPivotFlightPlanRequest:
    if not isinstance(request, VisionPivotFlightPlanRequest):
        raise TypeError("request must be VisionPivotFlightPlanRequest.")
    if request.current_cpr.trading_date != request.trading_date:
        raise ValueError("current CPR trading date mismatch.")
    if request.current_camarilla.trading_date != request.trading_date:
        raise ValueError("current Camarilla trading date mismatch.")
    dates = [item.trading_date for item in request.historical_daily_ohlc]
    if len(set(dates)) != len(dates):
        raise ValueError("historical_daily_ohlc contains duplicate trading dates.")
    return request


def classify_pivot_relationship(
    current_range: tuple[float, float],
    prior_range: tuple[float, float],
    *,
    tolerance: float,
) -> VisionPivotRelationship:
    current_low, current_high = _normalize_range(current_range)
    prior_low, prior_high = _normalize_range(prior_range)
    current_width = current_high - current_low
    prior_width = prior_high - prior_low
    reference = max(current_width, prior_width, 1.0)
    current_mid = (current_low + current_high) / 2.0
    prior_mid = (prior_low + prior_high) / 2.0
    if abs(current_low - prior_low) <= reference * tolerance and abs(current_high - prior_high) <= reference * tolerance:
        return VisionPivotRelationship.UNCHANGED_VALUE
    if current_low > prior_high:
        return VisionPivotRelationship.HIGHER_VALUE
    if current_high < prior_low:
        return VisionPivotRelationship.LOWER_VALUE
    if current_low >= prior_low and current_high <= prior_high:
        return VisionPivotRelationship.INSIDE_VALUE
    if current_low <= prior_low and current_high >= prior_high:
        return VisionPivotRelationship.OUTSIDE_VALUE
    if current_mid > prior_mid:
        return VisionPivotRelationship.OVERLAPPING_HIGHER_VALUE
    if current_mid < prior_mid:
        return VisionPivotRelationship.OVERLAPPING_LOWER_VALUE
    return VisionPivotRelationship.UNCHANGED_VALUE


def classify_width(
    width: float,
    historical_widths: tuple[float, ...],
    *,
    configuration: VisionPivotContextConfiguration,
) -> VisionPivotWidthState:
    width = _finite_number(width, "width")
    if width < 0:
        raise ValueError("width cannot be negative.")
    sample = tuple(_finite_number(item, "historical_width") for item in historical_widths if item > 0)
    if len(sample) < configuration.pivot_width_history_sessions:
        return VisionPivotWidthState.INSUFFICIENT_DATA
    baseline = median(sample[-configuration.pivot_width_history_sessions :])
    if baseline <= 0:
        return VisionPivotWidthState.INSUFFICIENT_DATA
    ratio = width / baseline
    if ratio <= configuration.narrow_width_ratio:
        return VisionPivotWidthState.NARROW
    if ratio >= configuration.wide_width_ratio:
        return VisionPivotWidthState.WIDE
    return VisionPivotWidthState.NORMAL


def _directional_prior(relationship: VisionPivotRelationship) -> VisionPivotDirectionalPrior:
    mapping = {
        VisionPivotRelationship.HIGHER_VALUE: VisionPivotDirectionalPrior.BULLISH,
        VisionPivotRelationship.OVERLAPPING_HIGHER_VALUE: VisionPivotDirectionalPrior.MODERATELY_BULLISH,
        VisionPivotRelationship.LOWER_VALUE: VisionPivotDirectionalPrior.BEARISH,
        VisionPivotRelationship.OVERLAPPING_LOWER_VALUE: VisionPivotDirectionalPrior.MODERATELY_BEARISH,
        VisionPivotRelationship.INSIDE_VALUE: VisionPivotDirectionalPrior.BREAKOUT_UNRESOLVED,
        VisionPivotRelationship.OUTSIDE_VALUE: VisionPivotDirectionalPrior.RANGE_BALANCE,
        VisionPivotRelationship.UNCHANGED_VALUE: VisionPivotDirectionalPrior.BALANCE_NEUTRAL,
        VisionPivotRelationship.INSUFFICIENT_DATA: VisionPivotDirectionalPrior.INSUFFICIENT_DATA,
    }
    return mapping[relationship]


def _combined_context(
    cpr_relationship: VisionPivotRelationship,
    cpr_width: VisionPivotWidthState,
    cpr_prior: VisionPivotDirectionalPrior,
    camarilla_relationship: VisionPivotRelationship,
    camarilla_width: VisionPivotWidthState,
    camarilla_prior: VisionPivotDirectionalPrior,
) -> tuple[VisionPivotCombinedContext, VisionPivotDirectionalPrior, tuple[str, ...]]:
    directional = {
        VisionPivotDirectionalPrior.BULLISH,
        VisionPivotDirectionalPrior.MODERATELY_BULLISH,
        VisionPivotDirectionalPrior.BEARISH,
        VisionPivotDirectionalPrior.MODERATELY_BEARISH,
    }
    if VisionPivotDirectionalPrior.INSUFFICIENT_DATA in {cpr_prior, camarilla_prior}:
        return (
            VisionPivotCombinedContext.INSUFFICIENT_DATA,
            VisionPivotDirectionalPrior.INSUFFICIENT_DATA,
            (),
        )
    if cpr_prior in {VisionPivotDirectionalPrior.BULLISH, VisionPivotDirectionalPrior.MODERATELY_BULLISH} and camarilla_prior in {
        VisionPivotDirectionalPrior.BEARISH,
        VisionPivotDirectionalPrior.MODERATELY_BEARISH,
    }:
        return (
            VisionPivotCombinedContext.CONFLICTED,
            VisionPivotDirectionalPrior.CONFLICTED,
            (f"CPR {cpr_relationship.value} conflicts with Camarilla {camarilla_relationship.value}",),
        )
    if cpr_prior in {VisionPivotDirectionalPrior.BEARISH, VisionPivotDirectionalPrior.MODERATELY_BEARISH} and camarilla_prior in {
        VisionPivotDirectionalPrior.BULLISH,
        VisionPivotDirectionalPrior.MODERATELY_BULLISH,
    }:
        return (
            VisionPivotCombinedContext.CONFLICTED,
            VisionPivotDirectionalPrior.CONFLICTED,
            (f"CPR {cpr_relationship.value} conflicts with Camarilla {camarilla_relationship.value}",),
        )
    if cpr_prior is VisionPivotDirectionalPrior.BULLISH and camarilla_prior is VisionPivotDirectionalPrior.BULLISH:
        return VisionPivotCombinedContext.BULLISH_ALIGNED, VisionPivotDirectionalPrior.BULLISH, ()
    if cpr_prior is VisionPivotDirectionalPrior.BEARISH and camarilla_prior is VisionPivotDirectionalPrior.BEARISH:
        return VisionPivotCombinedContext.BEARISH_ALIGNED, VisionPivotDirectionalPrior.BEARISH, ()
    if cpr_relationship is VisionPivotRelationship.INSIDE_VALUE and camarilla_relationship is VisionPivotRelationship.INSIDE_VALUE and (
        cpr_width is VisionPivotWidthState.NARROW or camarilla_width is VisionPivotWidthState.NARROW
    ):
        return (
            VisionPivotCombinedContext.BREAKOUT_POTENTIAL,
            VisionPivotDirectionalPrior.BREAKOUT_UNRESOLVED,
            (),
        )
    if cpr_relationship is VisionPivotRelationship.OUTSIDE_VALUE or camarilla_relationship is VisionPivotRelationship.OUTSIDE_VALUE:
        if cpr_width is VisionPivotWidthState.WIDE or camarilla_width is VisionPivotWidthState.WIDE:
            return VisionPivotCombinedContext.BALANCE_RANGE, VisionPivotDirectionalPrior.RANGE_BALANCE, ()
    if cpr_prior in directional and camarilla_prior in directional:
        if cpr_prior in {VisionPivotDirectionalPrior.BULLISH, VisionPivotDirectionalPrior.MODERATELY_BULLISH}:
            return VisionPivotCombinedContext.MODERATELY_BULLISH, VisionPivotDirectionalPrior.MODERATELY_BULLISH, ()
        return VisionPivotCombinedContext.MODERATELY_BEARISH, VisionPivotDirectionalPrior.MODERATELY_BEARISH, ()
    if cpr_width is VisionPivotWidthState.NARROW and camarilla_width is VisionPivotWidthState.NARROW:
        return VisionPivotCombinedContext.BREAKOUT_POTENTIAL, VisionPivotDirectionalPrior.BREAKOUT_UNRESOLVED, ()
    if cpr_width is VisionPivotWidthState.WIDE and camarilla_width is VisionPivotWidthState.WIDE:
        return VisionPivotCombinedContext.BALANCE_RANGE, VisionPivotDirectionalPrior.RANGE_BALANCE, ()
    return VisionPivotCombinedContext.NEUTRAL, VisionPivotDirectionalPrior.BALANCE_NEUTRAL, ()


def _expansion_tendency(
    context: VisionPivotCombinedContext,
    cpr_width: VisionPivotWidthState,
    camarilla_width: VisionPivotWidthState,
) -> VisionPivotTendency:
    if VisionPivotWidthState.INSUFFICIENT_DATA in {cpr_width, camarilla_width}:
        return VisionPivotTendency.INSUFFICIENT_DATA
    if context is VisionPivotCombinedContext.BREAKOUT_POTENTIAL:
        return VisionPivotTendency.HIGH
    if cpr_width is VisionPivotWidthState.NARROW or camarilla_width is VisionPivotWidthState.NARROW:
        return VisionPivotTendency.MODERATE
    return VisionPivotTendency.LOW


def _balance_tendency(
    context: VisionPivotCombinedContext,
    cpr_width: VisionPivotWidthState,
    camarilla_width: VisionPivotWidthState,
) -> VisionPivotTendency:
    if VisionPivotWidthState.INSUFFICIENT_DATA in {cpr_width, camarilla_width}:
        return VisionPivotTendency.INSUFFICIENT_DATA
    if context is VisionPivotCombinedContext.BALANCE_RANGE:
        return VisionPivotTendency.HIGH
    if cpr_width is VisionPivotWidthState.WIDE or camarilla_width is VisionPivotWidthState.WIDE:
        return VisionPivotTendency.MODERATE
    return VisionPivotTendency.LOW


def _supporting_reasons(
    cpr_relationship: VisionPivotRelationship,
    cpr_width: VisionPivotWidthState,
    cpr_prior: VisionPivotDirectionalPrior,
    camarilla_relationship: VisionPivotRelationship,
    camarilla_width: VisionPivotWidthState,
    camarilla_prior: VisionPivotDirectionalPrior,
    combined: VisionPivotCombinedContext,
    expansion: VisionPivotTendency,
    balance: VisionPivotTendency,
) -> tuple[str, ...]:
    return _normalize_unique_text_tuple(
        (
            f"CPR relationship {cpr_relationship.value}",
            f"CPR width {cpr_width.value}",
            f"CPR prior {cpr_prior.value}",
            f"Camarilla relationship {camarilla_relationship.value}",
            f"Camarilla width {camarilla_width.value}",
            f"Camarilla prior {camarilla_prior.value}",
            f"Combined pivot context {combined.value}",
            f"Expansion tendency {expansion.value}",
            f"Balance tendency {balance.value}",
            "Opening confirmation required",
        ),
        "supporting_reasons",
    )


def _bullish_zones(
    relationship: VisionPivotRelationship,
    combined: VisionPivotCombinedContext,
) -> tuple[VisionPivotActionZone, ...]:
    zones = [
        VisionPivotActionZone("H3_IF_OPEN_ABOVE_H3", "conditional_on_opening_above_h3", "Camarilla"),
        VisionPivotActionZone("L3_IF_OPEN_BETWEEN_L3_H3", "conditional_on_opening_between_l3_h3", "Camarilla"),
    ]
    if relationship is VisionPivotRelationship.INSIDE_VALUE or combined is VisionPivotCombinedContext.BREAKOUT_POTENTIAL:
        zones.append(VisionPivotActionZone("H4_BULLISH_ACCEPTANCE_AREA", "requires_opening_and_breakout_acceptance", "Camarilla"))
    return tuple(zones)


def _bearish_zones(
    relationship: VisionPivotRelationship,
    combined: VisionPivotCombinedContext,
) -> tuple[VisionPivotActionZone, ...]:
    zones = [
        VisionPivotActionZone("L3_IF_OPEN_BELOW_L3", "conditional_on_opening_below_l3", "Camarilla"),
        VisionPivotActionZone("H3_IF_OPEN_BETWEEN_L3_H3", "conditional_on_opening_between_l3_h3", "Camarilla"),
    ]
    if relationship is VisionPivotRelationship.INSIDE_VALUE or combined is VisionPivotCombinedContext.BREAKOUT_POTENTIAL:
        zones.append(VisionPivotActionZone("L4_BEARISH_ACCEPTANCE_AREA", "requires_opening_and_breakout_acceptance", "Camarilla"))
    return tuple(zones)


def _neutral_scenario(context: VisionPivotCombinedContext) -> str:
    if context is VisionPivotCombinedContext.BREAKOUT_POTENTIAL:
        return "Inside value and narrow width indicate breakout potential; direction remains unresolved before opening confirmation."
    if context is VisionPivotCombinedContext.BALANCE_RANGE:
        return "Outside or wide pivot context indicates balance/range tendency before opening confirmation."
    if context is VisionPivotCombinedContext.CONFLICTED:
        return "CPR and Camarilla disagree; opening behavior must resolve the conflict."
    return "Neutral pivot context; opening behavior must confirm or reject the provisional plan."


def _previous_daily_for_reference(history: tuple[DailyOHLC, ...], reference_date: date) -> DailyOHLC | None:
    prior = tuple(sorted((item for item in history if item.trading_date < reference_date), key=lambda item: item.trading_date))
    return prior[-1] if prior else None


def _historical_cpr_widths(history: tuple[DailyOHLC, ...], reference_date: date) -> tuple[float, ...]:
    return tuple(CPRCalculator.calculate(item).width for item in sorted(history, key=lambda value: value.trading_date) if item.trading_date < reference_date)


def _historical_camarilla_widths(history: tuple[DailyOHLC, ...], reference_date: date) -> tuple[float, ...]:
    return tuple(
        abs(levels.h3 - levels.l3)
        for levels in (
            CamarillaCalculator.calculate(item)
            for item in sorted(history, key=lambda value: value.trading_date)
            if item.trading_date < reference_date
        )
    )


def _cpr_range(levels: CPRLevels) -> tuple[float, float]:
    return min(levels.bc, levels.tc), max(levels.bc, levels.tc)


def _camarilla_h3_l3_range(levels: CamarillaLevels) -> tuple[float, float]:
    return min(levels.l3, levels.h3), max(levels.l3, levels.h3)


def _normalize_range(values: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(values, tuple) or len(values) != 2:
        raise TypeError("pivot range must be a two-item tuple.")
    low = _finite_number(values[0], "range_low")
    high = _finite_number(values[1], "range_high")
    if high < low:
        raise ValueError("range high cannot be below low.")
    return low, high


def _normalize_zones(values: tuple[VisionPivotActionZone, ...], field_name: str) -> tuple[VisionPivotActionZone, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple.")
    for value in values:
        if not isinstance(value, VisionPivotActionZone):
            raise TypeError(f"{field_name} must contain VisionPivotActionZone values.")
    return values


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


def _require_enum(value, expected_type, field_name: str) -> None:
    if not isinstance(value, expected_type):
        raise TypeError(f"{field_name} must be {expected_type.__name__}.")


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


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
