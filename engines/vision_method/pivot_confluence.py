"""
Deterministic Pivot Hot Zone and Action-Zone confluence.

VPM_CONFLUENCE_1 consumes existing immutable Vision Method contexts and labels
areas where independent reference families cluster. It does not calculate
indicators, generate entries, or create trade candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame

from .enums import (
    VisionCHoCH,
    VisionFairValueGapDirection,
    VisionLevelQuality,
    VisionLiquiditySweep,
    VisionOpeningAcceptanceState,
    VisionOpeningScenario,
    VisionOpeningScenarioDirection,
    VisionOptionConfirmation,
    VisionPivotCombinedContext,
    VisionPivotDirectionalPrior,
    VisionPivotPriceRelation,
    VisionPivotReferenceFamily,
    VisionPivotReferenceKind,
    VisionPivotZoneAlignment,
    VisionPivotZoneDirectionalRole,
    VisionPivotZoneQuality,
    VisionPivotZoneStatus,
    VisionPivotZoneStrength,
    VisionPivotZoneType,
    VisionStructureTrend,
    VisionSwingType,
)
from .models import (
    VisionLevelContext,
    VisionLiquidityContext,
    VisionOpeningRangeContext,
    VisionStructureContext,
)
from .opening_assessment import VisionPivotOpeningAssessment
from .pivot_context import VisionPivotFlightPlan


@dataclass(frozen=True, slots=True)
class VisionPivotConfluenceConfiguration:
    confluence_proximity_bps: float = 15.0
    zone_merge_tolerance_bps: float = 5.0
    minimum_independent_families: int = 2
    max_active_hot_zones: int = 12
    max_zone_width_bps: float = 50.0

    def __post_init__(self) -> None:
        for field_name in ("confluence_proximity_bps", "zone_merge_tolerance_bps", "max_zone_width_bps"):
            value = _finite_number(getattr(self, field_name), field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive.")
            object.__setattr__(self, field_name, value)
        if isinstance(self.minimum_independent_families, bool) or not isinstance(self.minimum_independent_families, int):
            raise TypeError("minimum_independent_families must be int.")
        if self.minimum_independent_families < 2:
            raise ValueError("minimum_independent_families must be at least 2.")
        if isinstance(self.max_active_hot_zones, bool) or not isinstance(self.max_active_hot_zones, int):
            raise TypeError("max_active_hot_zones must be int.")
        if self.max_active_hot_zones < 1:
            raise ValueError("max_active_hot_zones must be positive.")


@dataclass(frozen=True, slots=True)
class VisionPivotZoneMember:
    family: VisionPivotReferenceFamily
    kind: VisionPivotReferenceKind
    label: str
    price: float
    role_hint: VisionPivotZoneDirectionalRole
    status: VisionPivotZoneStatus = VisionPivotZoneStatus.ACTIVE

    def __post_init__(self) -> None:
        _require_enum(self.family, VisionPivotReferenceFamily, "family")
        _require_enum(self.kind, VisionPivotReferenceKind, "kind")
        object.__setattr__(self, "label", _normalize_text(self.label, "label"))
        object.__setattr__(self, "price", _positive_number(self.price, "price"))
        _require_enum(self.role_hint, VisionPivotZoneDirectionalRole, "role_hint")
        _require_enum(self.status, VisionPivotZoneStatus, "status")


@dataclass(frozen=True, slots=True)
class VisionPivotHotZone:
    instrument: RuntimeInstrument
    trading_date: date
    zone_low: float
    zone_high: float
    zone_center: float
    member_references: tuple[VisionPivotZoneMember, ...]
    reference_families: tuple[VisionPivotReferenceFamily, ...]
    independent_family_count: int
    zone_type: VisionPivotZoneType
    directional_role: VisionPivotZoneDirectionalRole
    quality: VisionPivotZoneQuality
    strength: VisionPivotZoneStrength
    active_scenario_alignment: VisionPivotZoneAlignment
    opening_assessment_alignment: VisionPivotZoneAlignment
    status: VisionPivotZoneStatus
    supporting_reasons: tuple[str, ...]
    conflicting_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    current_price_relation: VisionPivotPriceRelation
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date.")
        low = _positive_number(self.zone_low, "zone_low")
        high = _positive_number(self.zone_high, "zone_high")
        center = _positive_number(self.zone_center, "zone_center")
        if high < low:
            raise ValueError("zone_high cannot be below zone_low.")
        if center < low or center > high:
            raise ValueError("zone_center must be inside the zone band.")
        members = _normalize_members(self.member_references)
        families = _families(members)
        if self.reference_families != families:
            object.__setattr__(self, "reference_families", families)
        if self.independent_family_count != len(families):
            object.__setattr__(self, "independent_family_count", len(families))
        _require_enum(self.zone_type, VisionPivotZoneType, "zone_type")
        _require_enum(self.directional_role, VisionPivotZoneDirectionalRole, "directional_role")
        _require_enum(self.quality, VisionPivotZoneQuality, "quality")
        _require_enum(self.strength, VisionPivotZoneStrength, "strength")
        _require_enum(self.active_scenario_alignment, VisionPivotZoneAlignment, "active_scenario_alignment")
        _require_enum(self.opening_assessment_alignment, VisionPivotZoneAlignment, "opening_assessment_alignment")
        _require_enum(self.status, VisionPivotZoneStatus, "status")
        _require_enum(self.current_price_relation, VisionPivotPriceRelation, "current_price_relation")
        _validate_aware(self.created_at, "created_at")
        if self.created_at.date() != self.trading_date:
            raise ValueError("created_at trading date mismatch.")
        object.__setattr__(self, "zone_low", low)
        object.__setattr__(self, "zone_high", high)
        object.__setattr__(self, "zone_center", center)
        object.__setattr__(self, "member_references", members)
        object.__setattr__(self, "supporting_reasons", _normalize_unique_text_tuple(self.supporting_reasons, "supporting_reasons"))
        object.__setattr__(self, "conflicting_reasons", _normalize_unique_text_tuple(self.conflicting_reasons, "conflicting_reasons"))
        object.__setattr__(self, "warnings", _normalize_unique_text_tuple(self.warnings, "warnings"))


@dataclass(frozen=True, slots=True)
class VisionPivotConfluenceContext:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    trading_date: date
    timestamp: datetime
    hot_zones: tuple[VisionPivotHotZone, ...]
    top_bullish_interest_zones: tuple[VisionPivotHotZone, ...]
    top_bearish_interest_zones: tuple[VisionPivotHotZone, ...]
    top_breakout_decision_zones: tuple[VisionPivotHotZone, ...]
    top_neutral_or_target_zones: tuple[VisionPivotHotZone, ...]
    quality: VisionLevelQuality
    status: VisionPivotZoneStatus
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date.")
        _validate_aware(self.timestamp, "timestamp")
        if self.timestamp.date() != self.trading_date:
            raise ValueError("timestamp trading date mismatch.")
        zones = _normalize_zones(self.hot_zones, "hot_zones", self.instrument, self.trading_date)
        object.__setattr__(self, "hot_zones", zones)
        object.__setattr__(self, "top_bullish_interest_zones", _subset_zones(self.top_bullish_interest_zones, zones, "top_bullish_interest_zones"))
        object.__setattr__(self, "top_bearish_interest_zones", _subset_zones(self.top_bearish_interest_zones, zones, "top_bearish_interest_zones"))
        object.__setattr__(self, "top_breakout_decision_zones", _subset_zones(self.top_breakout_decision_zones, zones, "top_breakout_decision_zones"))
        object.__setattr__(self, "top_neutral_or_target_zones", _subset_zones(self.top_neutral_or_target_zones, zones, "top_neutral_or_target_zones"))
        _require_enum(self.quality, VisionLevelQuality, "quality")
        _require_enum(self.status, VisionPivotZoneStatus, "status")
        object.__setattr__(self, "warnings", _normalize_unique_text_tuple(self.warnings, "warnings"))


@dataclass(frozen=True, slots=True)
class VisionPivotConfluenceRequest:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    trading_date: date
    timestamp: datetime
    current_price: float
    level_context: VisionLevelContext
    opening_range_context: VisionOpeningRangeContext | None = None
    structure_context: VisionStructureContext | None = None
    liquidity_context: VisionLiquidityContext | None = None
    pivot_flight_plan: VisionPivotFlightPlan | None = None
    pivot_opening_assessment: VisionPivotOpeningAssessment | None = None
    configuration: VisionPivotConfluenceConfiguration = field(default_factory=VisionPivotConfluenceConfiguration)

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date.")
        _validate_aware(self.timestamp, "timestamp")
        if self.timestamp.date() != self.trading_date:
            raise ValueError("timestamp trading date mismatch.")
        object.__setattr__(self, "current_price", _positive_number(self.current_price, "current_price"))
        if not isinstance(self.level_context, VisionLevelContext):
            raise TypeError("level_context must be VisionLevelContext.")
        if self.opening_range_context is not None and not isinstance(self.opening_range_context, VisionOpeningRangeContext):
            raise TypeError("opening_range_context must be VisionOpeningRangeContext or None.")
        if self.structure_context is not None and not isinstance(self.structure_context, VisionStructureContext):
            raise TypeError("structure_context must be VisionStructureContext or None.")
        if self.liquidity_context is not None and not isinstance(self.liquidity_context, VisionLiquidityContext):
            raise TypeError("liquidity_context must be VisionLiquidityContext or None.")
        if self.pivot_flight_plan is not None:
            if not isinstance(self.pivot_flight_plan, VisionPivotFlightPlan):
                raise TypeError("pivot_flight_plan must be VisionPivotFlightPlan or None.")
            if self.pivot_flight_plan.instrument is not self.instrument:
                raise ValueError("pivot_flight_plan instrument mismatch.")
            if self.pivot_flight_plan.trading_date != self.trading_date:
                raise ValueError("pivot_flight_plan trading date mismatch.")
        if self.pivot_opening_assessment is not None:
            if not isinstance(self.pivot_opening_assessment, VisionPivotOpeningAssessment):
                raise TypeError("pivot_opening_assessment must be VisionPivotOpeningAssessment or None.")
            if self.pivot_opening_assessment.instrument is not self.instrument:
                raise ValueError("pivot_opening_assessment instrument mismatch.")
            if self.pivot_opening_assessment.trading_date != self.trading_date:
                raise ValueError("pivot_opening_assessment trading date mismatch.")
        if not isinstance(self.configuration, VisionPivotConfluenceConfiguration):
            raise TypeError("configuration must be VisionPivotConfluenceConfiguration.")


def build_pivot_confluence_context(request: VisionPivotConfluenceRequest) -> VisionPivotConfluenceContext:
    validate_pivot_confluence_request(request)
    members = _reference_members(request)
    warnings: list[str] = []
    if len(_families(members)) < request.configuration.minimum_independent_families:
        warnings.append("Fewer than two independent reference families available")
    clusters = _clusters(members, request.configuration)
    zones = [_zone_from_cluster(cluster, request) for cluster in clusters if len(_families(cluster)) >= request.configuration.minimum_independent_families]
    zones = _merge_overlapping_zones(zones, request)
    zones = tuple(sorted(zones, key=_zone_sort_key)[: request.configuration.max_active_hot_zones])
    quality = VisionLevelQuality.FULL if zones else VisionLevelQuality.INSUFFICIENT
    if zones and any(zone.quality in {VisionPivotZoneQuality.LOW, VisionPivotZoneQuality.MEDIUM} for zone in zones):
        quality = VisionLevelQuality.PARTIAL
    status = VisionPivotZoneStatus.ACTIVE if zones else VisionPivotZoneStatus.STALE
    return VisionPivotConfluenceContext(
        instrument=request.instrument,
        timeframe=request.timeframe,
        trading_date=request.trading_date,
        timestamp=request.timestamp,
        hot_zones=zones,
        top_bullish_interest_zones=_top_role(zones, {VisionPivotZoneDirectionalRole.BULLISH_SUPPORT}),
        top_bearish_interest_zones=_top_role(zones, {VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE}),
        top_breakout_decision_zones=_top_role(
            zones,
            {VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE, VisionPivotZoneDirectionalRole.BREAKDOWN_DOWNSIDE},
        ),
        top_neutral_or_target_zones=_top_role(zones, {VisionPivotZoneDirectionalRole.TARGET_MAGNET, VisionPivotZoneDirectionalRole.NEUTRAL}),
        quality=quality,
        status=status,
        warnings=tuple(warnings),
    )


def validate_pivot_confluence_request(request: VisionPivotConfluenceRequest) -> VisionPivotConfluenceRequest:
    if not isinstance(request, VisionPivotConfluenceRequest):
        raise TypeError("request must be VisionPivotConfluenceRequest.")
    return request


def _reference_members(request: VisionPivotConfluenceRequest) -> tuple[VisionPivotZoneMember, ...]:
    level = request.level_context
    cpr = level.cpr_context
    cama = level.camarilla_context
    previous = level.previous_day_context
    members = [
        _member(VisionPivotReferenceFamily.CPR, VisionPivotReferenceKind.CPR_BC, "CPR BC", cpr.bc, VisionPivotZoneDirectionalRole.BULLISH_SUPPORT),
        _member(VisionPivotReferenceFamily.CPR, VisionPivotReferenceKind.CPR_TC, "CPR TC", cpr.tc, VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE),
        _member(VisionPivotReferenceFamily.CPR, VisionPivotReferenceKind.CPR_PIVOT, "CPR Pivot", cpr.pivot, VisionPivotZoneDirectionalRole.TARGET_MAGNET),
        _member(VisionPivotReferenceFamily.CAMARILLA, VisionPivotReferenceKind.CAMARILLA_H3, "Camarilla H3", cama.h3, VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE),
        _member(VisionPivotReferenceFamily.CAMARILLA, VisionPivotReferenceKind.CAMARILLA_H4, "Camarilla H4", cama.h4, VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE),
        _member(VisionPivotReferenceFamily.CAMARILLA, VisionPivotReferenceKind.CAMARILLA_H5, "Camarilla H5", cama.h5, VisionPivotZoneDirectionalRole.TARGET_MAGNET),
        _member(VisionPivotReferenceFamily.CAMARILLA, VisionPivotReferenceKind.CAMARILLA_H6, "Camarilla H6", cama.h6, VisionPivotZoneDirectionalRole.TARGET_MAGNET),
        _member(VisionPivotReferenceFamily.CAMARILLA, VisionPivotReferenceKind.CAMARILLA_L3, "Camarilla L3", cama.l3, VisionPivotZoneDirectionalRole.BULLISH_SUPPORT),
        _member(VisionPivotReferenceFamily.CAMARILLA, VisionPivotReferenceKind.CAMARILLA_L4, "Camarilla L4", cama.l4, VisionPivotZoneDirectionalRole.BREAKDOWN_DOWNSIDE),
        _member(VisionPivotReferenceFamily.CAMARILLA, VisionPivotReferenceKind.CAMARILLA_L5, "Camarilla L5", cama.l5, VisionPivotZoneDirectionalRole.TARGET_MAGNET),
        _member(VisionPivotReferenceFamily.CAMARILLA, VisionPivotReferenceKind.CAMARILLA_L6, "Camarilla L6", cama.l6, VisionPivotZoneDirectionalRole.TARGET_MAGNET),
        _member(VisionPivotReferenceFamily.PRIOR_SESSION, VisionPivotReferenceKind.PRIOR_HIGH, "Previous High", previous.previous_high, VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE),
        _member(VisionPivotReferenceFamily.PRIOR_SESSION, VisionPivotReferenceKind.PRIOR_LOW, "Previous Low", previous.previous_low, VisionPivotZoneDirectionalRole.BULLISH_SUPPORT),
        _member(VisionPivotReferenceFamily.PRIOR_SESSION, VisionPivotReferenceKind.PRIOR_CLOSE, "Previous Close", previous.previous_close, VisionPivotZoneDirectionalRole.TARGET_MAGNET),
    ]
    if level.vwap_context is not None:
        members.append(_member(VisionPivotReferenceFamily.VWAP, VisionPivotReferenceKind.VWAP, "VWAP", level.vwap_context.vwap, VisionPivotZoneDirectionalRole.NEUTRAL))
    if request.opening_range_context is not None and request.opening_range_context.quality is not VisionLevelQuality.INSUFFICIENT:
        opening = request.opening_range_context
        members.extend(
            (
                _member(VisionPivotReferenceFamily.OPENING_RANGE, VisionPivotReferenceKind.OPENING_RANGE_HIGH, "Opening Range High", opening.opening_high, VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE),
                _member(VisionPivotReferenceFamily.OPENING_RANGE, VisionPivotReferenceKind.OPENING_RANGE_LOW, "Opening Range Low", opening.opening_low, VisionPivotZoneDirectionalRole.BREAKDOWN_DOWNSIDE),
            )
        )
    if request.structure_context is not None and request.structure_context.quality is not VisionLevelQuality.INSUFFICIENT:
        structure = request.structure_context
        if structure.current_swing_high is not None:
            members.append(_member(VisionPivotReferenceFamily.STRUCTURE, VisionPivotReferenceKind.SWING_HIGH, "Swing High", structure.current_swing_high.price, VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE))
        if structure.current_swing_low is not None:
            members.append(_member(VisionPivotReferenceFamily.STRUCTURE, VisionPivotReferenceKind.SWING_LOW, "Swing Low", structure.current_swing_low.price, VisionPivotZoneDirectionalRole.BULLISH_SUPPORT))
    if request.liquidity_context is not None and request.liquidity_context.quality is not VisionLevelQuality.INSUFFICIENT:
        members.extend(_liquidity_members(request.liquidity_context))
    return tuple(sorted(_dedupe_members(members), key=lambda member: (member.price, member.family.value, member.kind.value, member.label)))


def _liquidity_members(context: VisionLiquidityContext) -> tuple[VisionPivotZoneMember, ...]:
    members: list[VisionPivotZoneMember] = []
    equal_high_status = VisionPivotZoneStatus.CONSUMED if context.liquidity_sweep is VisionLiquiditySweep.BUY_SIDE_SWEEP else VisionPivotZoneStatus.ACTIVE
    equal_low_status = VisionPivotZoneStatus.CONSUMED if context.liquidity_sweep is VisionLiquiditySweep.SELL_SIDE_SWEEP else VisionPivotZoneStatus.ACTIVE
    for index, level in enumerate(context.equal_highs, start=1):
        members.append(
            VisionPivotZoneMember(
                family=VisionPivotReferenceFamily.LIQUIDITY,
                kind=VisionPivotReferenceKind.EQUAL_HIGH,
                label=f"Equal High {index}",
                price=level.price,
                role_hint=VisionPivotZoneDirectionalRole.TARGET_MAGNET,
                status=equal_high_status,
            )
        )
    for index, level in enumerate(context.equal_lows, start=1):
        members.append(
            VisionPivotZoneMember(
                family=VisionPivotReferenceFamily.LIQUIDITY,
                kind=VisionPivotReferenceKind.EQUAL_LOW,
                label=f"Equal Low {index}",
                price=level.price,
                role_hint=VisionPivotZoneDirectionalRole.TARGET_MAGNET,
                status=equal_low_status,
            )
        )
    if context.fair_value_gap is not None:
        role = VisionPivotZoneDirectionalRole.BULLISH_SUPPORT
        if context.fair_value_gap.direction is VisionFairValueGapDirection.BEARISH:
            role = VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE
        price = (context.fair_value_gap.lower_bound + context.fair_value_gap.upper_bound) / 2.0
        members.append(_member(VisionPivotReferenceFamily.LIQUIDITY, VisionPivotReferenceKind.FAIR_VALUE_GAP, "Fair Value Gap", price, role))
    if context.order_block is not None:
        role = VisionPivotZoneDirectionalRole.BULLISH_SUPPORT if context.order_block.direction.value == "bullish" else VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE
        price = (context.order_block.low + context.order_block.high) / 2.0
        members.append(_member(VisionPivotReferenceFamily.LIQUIDITY, VisionPivotReferenceKind.ORDER_BLOCK, "Order Block", price, role))
    return tuple(members)


def _clusters(
    members: tuple[VisionPivotZoneMember, ...],
    configuration: VisionPivotConfluenceConfiguration,
) -> tuple[tuple[VisionPivotZoneMember, ...], ...]:
    clusters: list[list[VisionPivotZoneMember]] = []
    for member in members:
        tolerance = _tolerance(member.price, configuration.confluence_proximity_bps)
        if clusters and abs(member.price - _cluster_center(clusters[-1])) <= max(tolerance, _tolerance(_cluster_center(clusters[-1]), configuration.confluence_proximity_bps)):
            clusters[-1].append(member)
        else:
            clusters.append([member])
    return tuple(tuple(cluster) for cluster in clusters)


def _zone_from_cluster(
    cluster: tuple[VisionPivotZoneMember, ...],
    request: VisionPivotConfluenceRequest,
) -> VisionPivotHotZone:
    prices = tuple(member.price for member in cluster)
    low = min(prices)
    high = max(prices)
    center = (low + high) / 2.0
    role, zone_type, conflicts = _role_and_type(cluster, request)
    alignment = _scenario_alignment(role, request)
    quality = _quality(cluster, low, high, alignment, request.configuration)
    strength = _strength(quality, len(_families(cluster)))
    status = VisionPivotZoneStatus.CONSUMED if any(member.status is VisionPivotZoneStatus.CONSUMED for member in cluster) else VisionPivotZoneStatus.ACTIVE
    warnings = _warnings(cluster, low, high, request.configuration)
    supporting = _supporting_reasons(cluster, role, alignment)
    return VisionPivotHotZone(
        instrument=request.instrument,
        trading_date=request.trading_date,
        zone_low=low,
        zone_high=high,
        zone_center=center,
        member_references=cluster,
        reference_families=_families(cluster),
        independent_family_count=len(_families(cluster)),
        zone_type=zone_type,
        directional_role=role,
        quality=quality,
        strength=strength,
        active_scenario_alignment=alignment,
        opening_assessment_alignment=alignment,
        status=status,
        supporting_reasons=supporting,
        conflicting_reasons=conflicts,
        warnings=warnings,
        current_price_relation=_price_relation(request.current_price, low, high, request.configuration),
        created_at=request.timestamp,
    )


def _merge_overlapping_zones(
    zones: list[VisionPivotHotZone],
    request: VisionPivotConfluenceRequest,
) -> tuple[VisionPivotHotZone, ...]:
    if not zones:
        return ()
    ordered = sorted(zones, key=lambda zone: (zone.zone_low, zone.zone_high, zone.directional_role.value))
    merged: list[VisionPivotHotZone] = []
    for zone in ordered:
        if not merged:
            merged.append(zone)
            continue
        previous = merged[-1]
        tolerance = _tolerance(previous.zone_center, request.configuration.zone_merge_tolerance_bps)
        overlaps = zone.zone_low <= previous.zone_high + tolerance
        if overlaps and zone.directional_role is previous.directional_role:
            members = _dedupe_members([*previous.member_references, *zone.member_references])
            merged[-1] = _zone_from_cluster(tuple(sorted(members, key=lambda member: (member.price, member.family.value, member.kind.value))), request)
            continue
        if overlaps and zone.directional_role is not previous.directional_role:
            members = _dedupe_members([*previous.member_references, *zone.member_references])
            conflict_zone = _zone_from_cluster(tuple(sorted(members, key=lambda member: (member.price, member.family.value, member.kind.value))), request)
            merged[-1] = _replace_role(
                conflict_zone,
                VisionPivotZoneDirectionalRole.CONFLICT,
                VisionPivotZoneType.CONFLICT_ZONE,
                ("Opposing reference roles overlap inside the same price band",),
            )
            continue
        merged.append(zone)
    return tuple(merged)


def _role_and_type(
    cluster: tuple[VisionPivotZoneMember, ...],
    request: VisionPivotConfluenceRequest,
) -> tuple[VisionPivotZoneDirectionalRole, VisionPivotZoneType, tuple[str, ...]]:
    kinds = {member.kind for member in cluster}
    roles = {member.role_hint for member in cluster}
    scenario = request.pivot_opening_assessment.active_scenario if request.pivot_opening_assessment is not None else None
    conflicts: list[str] = []
    if VisionPivotZoneDirectionalRole.BULLISH_SUPPORT in roles and VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE in roles:
        if _has_cpr_h3(kinds):
            return VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE, VisionPivotZoneType.RESISTANCE_HOT_ZONE, ()
        if _has_cpr_l3(kinds):
            return VisionPivotZoneDirectionalRole.BULLISH_SUPPORT, VisionPivotZoneType.SUPPORT_HOT_ZONE, ()
        conflicts.append("Support and resistance references overlap")
        return VisionPivotZoneDirectionalRole.CONFLICT, VisionPivotZoneType.CONFLICT_ZONE, tuple(conflicts)
    if _has_cpr_h3(kinds):
        return VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE, VisionPivotZoneType.RESISTANCE_HOT_ZONE, ()
    if _has_cpr_l3(kinds):
        return VisionPivotZoneDirectionalRole.BULLISH_SUPPORT, VisionPivotZoneType.SUPPORT_HOT_ZONE, ()
    if VisionPivotReferenceKind.CAMARILLA_H4 in kinds or VisionPivotReferenceKind.OPENING_RANGE_HIGH in kinds:
        if scenario is VisionOpeningScenario.BULLISH_BREAKOUT_WATCH:
            return VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE, VisionPivotZoneType.BREAKOUT_DECISION_ZONE, ()
    if VisionPivotReferenceKind.CAMARILLA_L4 in kinds or VisionPivotReferenceKind.OPENING_RANGE_LOW in kinds:
        if scenario is VisionOpeningScenario.BEARISH_BREAKOUT_WATCH:
            return VisionPivotZoneDirectionalRole.BREAKDOWN_DOWNSIDE, VisionPivotZoneType.BREAKOUT_DECISION_ZONE, ()
    if roles == {VisionPivotZoneDirectionalRole.TARGET_MAGNET}:
        return VisionPivotZoneDirectionalRole.TARGET_MAGNET, VisionPivotZoneType.TARGET_MAGNET_ZONE, ()
    if VisionPivotZoneDirectionalRole.BULLISH_SUPPORT in roles:
        return VisionPivotZoneDirectionalRole.BULLISH_SUPPORT, VisionPivotZoneType.SUPPORT_HOT_ZONE, ()
    if VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE in roles:
        return VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE, VisionPivotZoneType.RESISTANCE_HOT_ZONE, ()
    if VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE in roles:
        return VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE, VisionPivotZoneType.BREAKOUT_DECISION_ZONE, ()
    if VisionPivotZoneDirectionalRole.BREAKDOWN_DOWNSIDE in roles:
        return VisionPivotZoneDirectionalRole.BREAKDOWN_DOWNSIDE, VisionPivotZoneType.BREAKOUT_DECISION_ZONE, ()
    return VisionPivotZoneDirectionalRole.NEUTRAL, VisionPivotZoneType.NEUTRAL_HOT_ZONE, ()


def _scenario_alignment(
    role: VisionPivotZoneDirectionalRole,
    request: VisionPivotConfluenceRequest,
) -> VisionPivotZoneAlignment:
    assessment = request.pivot_opening_assessment
    if assessment is None:
        plan = request.pivot_flight_plan
        if plan is None:
            return VisionPivotZoneAlignment.UNRESOLVED
        return _prior_alignment(role, plan.combined_directional_prior)
    if assessment.opening_acceptance_state is VisionOpeningAcceptanceState.REJECTED:
        return VisionPivotZoneAlignment.OPPOSED
    if assessment.scenario_direction is VisionOpeningScenarioDirection.BULLISH:
        if role in {VisionPivotZoneDirectionalRole.BULLISH_SUPPORT, VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE}:
            return VisionPivotZoneAlignment.ALIGNED
        if role in {VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE, VisionPivotZoneDirectionalRole.BREAKDOWN_DOWNSIDE}:
            return VisionPivotZoneAlignment.OPPOSED
    if assessment.scenario_direction is VisionOpeningScenarioDirection.BEARISH:
        if role in {VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE, VisionPivotZoneDirectionalRole.BREAKDOWN_DOWNSIDE}:
            return VisionPivotZoneAlignment.ALIGNED
        if role in {VisionPivotZoneDirectionalRole.BULLISH_SUPPORT, VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE}:
            return VisionPivotZoneAlignment.OPPOSED
    if assessment.scenario_direction is VisionOpeningScenarioDirection.NEUTRAL:
        return VisionPivotZoneAlignment.NEUTRAL
    if role is VisionPivotZoneDirectionalRole.CONFLICT:
        return VisionPivotZoneAlignment.OPPOSED
    return VisionPivotZoneAlignment.UNRESOLVED


def _prior_alignment(
    role: VisionPivotZoneDirectionalRole,
    prior: VisionPivotDirectionalPrior,
) -> VisionPivotZoneAlignment:
    if prior in {VisionPivotDirectionalPrior.BULLISH, VisionPivotDirectionalPrior.MODERATELY_BULLISH}:
        return VisionPivotZoneAlignment.ALIGNED if role in {VisionPivotZoneDirectionalRole.BULLISH_SUPPORT, VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE} else VisionPivotZoneAlignment.PARTIAL
    if prior in {VisionPivotDirectionalPrior.BEARISH, VisionPivotDirectionalPrior.MODERATELY_BEARISH}:
        return VisionPivotZoneAlignment.ALIGNED if role in {VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE, VisionPivotZoneDirectionalRole.BREAKDOWN_DOWNSIDE} else VisionPivotZoneAlignment.PARTIAL
    if prior in {VisionPivotDirectionalPrior.RANGE_BALANCE, VisionPivotDirectionalPrior.BALANCE_NEUTRAL}:
        return VisionPivotZoneAlignment.NEUTRAL
    if prior is VisionPivotDirectionalPrior.CONFLICTED:
        return VisionPivotZoneAlignment.OPPOSED
    return VisionPivotZoneAlignment.UNRESOLVED


def _quality(
    cluster: tuple[VisionPivotZoneMember, ...],
    low: float,
    high: float,
    alignment: VisionPivotZoneAlignment,
    configuration: VisionPivotConfluenceConfiguration,
) -> VisionPivotZoneQuality:
    families = len(_families(cluster))
    if any(member.status is VisionPivotZoneStatus.CONSUMED for member in cluster):
        return VisionPivotZoneQuality.LOW
    if _width_bps(low, high) > configuration.max_zone_width_bps:
        return VisionPivotZoneQuality.MEDIUM if families >= 3 else VisionPivotZoneQuality.LOW
    if families >= 4 and alignment is VisionPivotZoneAlignment.ALIGNED:
        return VisionPivotZoneQuality.VERY_HIGH
    if families >= 3 or alignment is VisionPivotZoneAlignment.ALIGNED:
        return VisionPivotZoneQuality.HIGH
    if alignment in {VisionPivotZoneAlignment.PARTIAL, VisionPivotZoneAlignment.NEUTRAL, VisionPivotZoneAlignment.UNRESOLVED}:
        return VisionPivotZoneQuality.MEDIUM
    return VisionPivotZoneQuality.LOW


def _strength(quality: VisionPivotZoneQuality, family_count: int) -> VisionPivotZoneStrength:
    if quality is VisionPivotZoneQuality.VERY_HIGH:
        return VisionPivotZoneStrength.VERY_STRONG
    if quality is VisionPivotZoneQuality.HIGH or family_count >= 3:
        return VisionPivotZoneStrength.STRONG
    if quality is VisionPivotZoneQuality.MEDIUM:
        return VisionPivotZoneStrength.MODERATE
    return VisionPivotZoneStrength.WEAK


def _warnings(
    cluster: tuple[VisionPivotZoneMember, ...],
    low: float,
    high: float,
    configuration: VisionPivotConfluenceConfiguration,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if any(member.status is VisionPivotZoneStatus.CONSUMED for member in cluster):
        warnings.append("Consumed liquidity member reduces zone strength")
    if _width_bps(low, high) > configuration.max_zone_width_bps:
        warnings.append("Confluence band is broad")
    return tuple(warnings)


def _supporting_reasons(
    cluster: tuple[VisionPivotZoneMember, ...],
    role: VisionPivotZoneDirectionalRole,
    alignment: VisionPivotZoneAlignment,
) -> tuple[str, ...]:
    labels = ", ".join(member.label for member in cluster)
    families = ", ".join(family.value for family in _families(cluster))
    return (
        f"Independent families: {families}",
        f"Members: {labels}",
        f"Directional role {role.value}",
        f"Scenario alignment {alignment.value}",
    )


def _price_relation(
    price: float,
    low: float,
    high: float,
    configuration: VisionPivotConfluenceConfiguration,
) -> VisionPivotPriceRelation:
    if low <= price <= high:
        return VisionPivotPriceRelation.INSIDE
    tolerance = _tolerance((low + high) / 2.0, configuration.confluence_proximity_bps)
    if abs(price - low) <= tolerance or abs(price - high) <= tolerance:
        return VisionPivotPriceRelation.APPROACHING
    if price < low:
        return VisionPivotPriceRelation.BELOW
    return VisionPivotPriceRelation.ABOVE


def _top_role(
    zones: tuple[VisionPivotHotZone, ...],
    roles: set[VisionPivotZoneDirectionalRole],
) -> tuple[VisionPivotHotZone, ...]:
    return tuple(zone for zone in zones if zone.directional_role in roles)[:3]


def _replace_role(
    zone: VisionPivotHotZone,
    role: VisionPivotZoneDirectionalRole,
    zone_type: VisionPivotZoneType,
    conflicts: tuple[str, ...],
) -> VisionPivotHotZone:
    return VisionPivotHotZone(
        instrument=zone.instrument,
        trading_date=zone.trading_date,
        zone_low=zone.zone_low,
        zone_high=zone.zone_high,
        zone_center=zone.zone_center,
        member_references=zone.member_references,
        reference_families=zone.reference_families,
        independent_family_count=zone.independent_family_count,
        zone_type=zone_type,
        directional_role=role,
        quality=VisionPivotZoneQuality.LOW,
        strength=VisionPivotZoneStrength.WEAK,
        active_scenario_alignment=VisionPivotZoneAlignment.OPPOSED,
        opening_assessment_alignment=VisionPivotZoneAlignment.OPPOSED,
        status=zone.status,
        supporting_reasons=zone.supporting_reasons,
        conflicting_reasons=conflicts,
        warnings=zone.warnings,
        current_price_relation=zone.current_price_relation,
        created_at=zone.created_at,
    )


def _zone_sort_key(zone: VisionPivotHotZone) -> tuple[int, int, int, float, float]:
    quality_rank = {
        VisionPivotZoneQuality.VERY_HIGH: 4,
        VisionPivotZoneQuality.HIGH: 3,
        VisionPivotZoneQuality.MEDIUM: 2,
        VisionPivotZoneQuality.LOW: 1,
    }[zone.quality]
    alignment_rank = {
        VisionPivotZoneAlignment.ALIGNED: 5,
        VisionPivotZoneAlignment.PARTIAL: 4,
        VisionPivotZoneAlignment.NEUTRAL: 3,
        VisionPivotZoneAlignment.UNRESOLVED: 2,
        VisionPivotZoneAlignment.OPPOSED: 1,
    }[zone.active_scenario_alignment]
    relation_rank = 0 if zone.current_price_relation is VisionPivotPriceRelation.INSIDE else 1
    return (-quality_rank, -zone.independent_family_count, -alignment_rank, relation_rank, zone.zone_center)


def _has_cpr_h3(kinds: set[VisionPivotReferenceKind]) -> bool:
    return VisionPivotReferenceKind.CAMARILLA_H3 in kinds and bool(
        kinds & {VisionPivotReferenceKind.CPR_TC, VisionPivotReferenceKind.CPR_PIVOT, VisionPivotReferenceKind.CPR_BC}
    )


def _has_cpr_l3(kinds: set[VisionPivotReferenceKind]) -> bool:
    return VisionPivotReferenceKind.CAMARILLA_L3 in kinds and bool(
        kinds & {VisionPivotReferenceKind.CPR_TC, VisionPivotReferenceKind.CPR_PIVOT, VisionPivotReferenceKind.CPR_BC}
    )


def _member(
    family: VisionPivotReferenceFamily,
    kind: VisionPivotReferenceKind,
    label: str,
    price: float,
    role: VisionPivotZoneDirectionalRole,
) -> VisionPivotZoneMember:
    return VisionPivotZoneMember(family=family, kind=kind, label=label, price=price, role_hint=role)


def _dedupe_members(values: list[VisionPivotZoneMember]) -> tuple[VisionPivotZoneMember, ...]:
    result: list[VisionPivotZoneMember] = []
    seen: set[tuple[VisionPivotReferenceFamily, VisionPivotReferenceKind, str, float]] = set()
    for member in values:
        key = (member.family, member.kind, member.label.casefold(), round(member.price, 8))
        if key not in seen:
            seen.add(key)
            result.append(member)
    return tuple(result)


def _families(members: tuple[VisionPivotZoneMember, ...]) -> tuple[VisionPivotReferenceFamily, ...]:
    return tuple(sorted({member.family for member in members}, key=lambda family: family.value))


def _cluster_center(cluster: list[VisionPivotZoneMember]) -> float:
    return sum(member.price for member in cluster) / len(cluster)


def _tolerance(price: float, bps: float) -> float:
    return abs(price) * bps / 10000.0


def _width_bps(low: float, high: float) -> float:
    center = max((low + high) / 2.0, 1.0)
    return abs(high - low) / center * 10000.0


def _normalize_members(values: tuple[VisionPivotZoneMember, ...]) -> tuple[VisionPivotZoneMember, ...]:
    if not isinstance(values, tuple):
        raise TypeError("member_references must be tuple.")
    for value in values:
        if not isinstance(value, VisionPivotZoneMember):
            raise TypeError("member_references must contain VisionPivotZoneMember values.")
    return tuple(sorted(values, key=lambda member: (member.price, member.family.value, member.kind.value, member.label)))


def _normalize_zones(
    values: tuple[VisionPivotHotZone, ...],
    field_name: str,
    instrument: RuntimeInstrument,
    trading_date: date,
) -> tuple[VisionPivotHotZone, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple.")
    for value in values:
        if not isinstance(value, VisionPivotHotZone):
            raise TypeError(f"{field_name} must contain VisionPivotHotZone values.")
        if value.instrument is not instrument:
            raise ValueError(f"{field_name} instrument mismatch.")
        if value.trading_date != trading_date:
            raise ValueError(f"{field_name} trading date mismatch.")
    return values


def _subset_zones(
    values: tuple[VisionPivotHotZone, ...],
    full_set: tuple[VisionPivotHotZone, ...],
    field_name: str,
) -> tuple[VisionPivotHotZone, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple.")
    full = set(full_set)
    for value in values:
        if value not in full:
            raise ValueError(f"{field_name} must contain zones from hot_zones.")
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
