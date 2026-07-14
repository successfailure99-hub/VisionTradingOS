"""
Stateless Market Context Engine V2 calculator.
"""

from engines.market_context_v2.adapters import (
    camarilla_evidence,
    cpr_evidence,
    option_chain_evidence,
    price_action_evidence,
    vwap_evidence,
)
from engines.market_context_v2.configuration import MarketContextV2Configuration
from engines.market_context_v2.enums import (
    EvidenceDirection,
    MarketConflictSeverity,
    MarketContextReadiness,
    MarketDirection,
    MarketEvidenceSource,
    MarketRegime,
    TradePosture,
)
from engines.market_context_v2.models import (
    EVIDENCE_ORDER,
    PRIMARY_SOURCES,
    MarketContextV2Input,
    MarketContextV2Snapshot,
    MarketEvidence,
    MarketEvidenceConflict,
)


_SEVERITY_RANK = {
    MarketConflictSeverity.NONE: 0,
    MarketConflictSeverity.LOW: 1,
    MarketConflictSeverity.MODERATE: 2,
    MarketConflictSeverity.HIGH: 3,
    MarketConflictSeverity.CRITICAL: 4,
}


class MarketContextV2Calculator:
    """
    Pure, deterministic Market Context V2 calculation.
    """

    def calculate(
        self,
        *,
        inputs: MarketContextV2Input,
        configuration: MarketContextV2Configuration,
    ) -> MarketContextV2Snapshot:
        if not isinstance(inputs, MarketContextV2Input):
            raise TypeError("inputs must be MarketContextV2Input")
        if not isinstance(configuration, MarketContextV2Configuration):
            raise TypeError("configuration must be MarketContextV2Configuration")

        evidence = (
            price_action_evidence(
                inputs.price_action,
                timestamp=inputs.timestamp,
                weight=configuration.price_action_weight,
            ),
            option_chain_evidence(
                inputs.option_chain_analytics,
                timestamp=inputs.timestamp,
                weight=configuration.option_chain_weight,
            ),
            camarilla_evidence(
                inputs.camarilla,
                current_price=inputs.current_price,
                timestamp=inputs.timestamp,
                weight=configuration.camarilla_weight,
            ),
            cpr_evidence(
                inputs.cpr,
                current_price=inputs.current_price,
                timestamp=inputs.timestamp,
                weight=configuration.cpr_weight,
            ),
            vwap_evidence(
                inputs.vwap,
                current_price=inputs.current_price,
                timestamp=inputs.timestamp,
                weight=configuration.vwap_weight,
            ),
        )

        conflicts = _detect_conflicts(evidence)
        conflict_severity = _max_severity(conflicts)
        primary_sources_available = sum(1 for item in evidence if item.primary and item.available)
        secondary_sources_available = sum(1 for item in evidence if not item.primary and item.available)
        readiness = _readiness(primary_sources_available, configuration)
        bullish_score = sum(item.score for item in evidence if item.score > 0)
        bearish_score = abs(sum(item.score for item in evidence if item.score < 0))
        net_score = bullish_score - bearish_score
        direction = _direction(
            evidence,
            conflicts,
            readiness,
            net_score,
            configuration,
            conflict_severity,
        )
        regime = _regime(direction, evidence, conflict_severity, readiness)
        trade_posture = _posture(direction, readiness, conflict_severity)
        confidence = _confidence(
            evidence,
            net_score,
            readiness,
            conflict_severity,
            any(conflict.primary_conflict for conflict in conflicts),
        )
        rationale = _rationale(evidence, conflicts, direction, readiness)
        warnings = _warnings(evidence, conflicts, readiness)

        return MarketContextV2Snapshot(
            instrument=inputs.instrument,
            timestamp=inputs.timestamp,
            readiness=readiness,
            direction=direction,
            regime=regime,
            trade_posture=trade_posture,
            conflict_severity=conflict_severity,
            bullish_score=bullish_score,
            bearish_score=bearish_score,
            net_score=net_score,
            confidence=confidence,
            evidence=evidence,
            conflicts=conflicts,
            price_action_evidence=evidence[0],
            option_chain_evidence=evidence[1],
            camarilla_evidence=evidence[2],
            cpr_evidence=evidence[3],
            vwap_evidence=evidence[4],
            current_price=inputs.current_price,
            reference_vwap=inputs.vwap.vwap if inputs.vwap is not None else None,
            primary_sources_available=primary_sources_available,
            secondary_sources_available=secondary_sources_available,
            rationale=rationale,
            warnings=warnings,
        )


def _detect_conflicts(
    evidence: tuple[MarketEvidence, ...],
) -> tuple[MarketEvidenceConflict, ...]:
    conflicts: list[MarketEvidenceConflict] = []
    ordered = sorted(evidence, key=lambda item: EVIDENCE_ORDER.index(item.source))
    for index, left in enumerate(ordered):
        if left.direction not in {EvidenceDirection.BULLISH, EvidenceDirection.BEARISH}:
            continue
        for right in ordered[index + 1:]:
            if {left.direction, right.direction} != {
                EvidenceDirection.BULLISH,
                EvidenceDirection.BEARISH,
            }:
                continue
            primary_conflict = left.primary and right.primary
            severity = _conflict_severity(left, right, primary_conflict)
            conflicts.append(
                MarketEvidenceConflict(
                    source_a=left.source,
                    direction_a=left.direction,
                    source_b=right.source,
                    direction_b=right.direction,
                    severity=severity,
                    primary_conflict=primary_conflict,
                    rationale=(
                        f"{left.source.value} {left.direction.value} evidence "
                        f"conflicts with {right.source.value} {right.direction.value} evidence."
                    ),
                )
            )
    return tuple(conflicts)


def _conflict_severity(
    left: MarketEvidence,
    right: MarketEvidence,
    primary_conflict: bool,
) -> MarketConflictSeverity:
    combined = abs(left.score) + abs(right.score)
    if primary_conflict and combined >= 20:
        return MarketConflictSeverity.CRITICAL
    if primary_conflict:
        return MarketConflictSeverity.HIGH
    if left.primary or right.primary:
        return MarketConflictSeverity.MODERATE
    if combined >= 8:
        return MarketConflictSeverity.MODERATE
    return MarketConflictSeverity.LOW


def _max_severity(
    conflicts: tuple[MarketEvidenceConflict, ...],
) -> MarketConflictSeverity:
    if not conflicts:
        return MarketConflictSeverity.NONE
    return max(conflicts, key=lambda item: _SEVERITY_RANK[item.severity]).severity


def _readiness(
    primary_sources_available: int,
    configuration: MarketContextV2Configuration,
) -> MarketContextReadiness:
    if primary_sources_available <= 0:
        return MarketContextReadiness.INSUFFICIENT
    if primary_sources_available >= configuration.minimum_primary_sources:
        return MarketContextReadiness.READY
    if configuration.allow_partial_secondary_inputs:
        return MarketContextReadiness.PARTIAL
    return MarketContextReadiness.INSUFFICIENT


def _direction(
    evidence: tuple[MarketEvidence, ...],
    conflicts: tuple[MarketEvidenceConflict, ...],
    readiness: MarketContextReadiness,
    net_score: int,
    configuration: MarketContextV2Configuration,
    conflict_severity: MarketConflictSeverity,
) -> MarketDirection:
    if readiness is MarketContextReadiness.INSUFFICIENT:
        return MarketDirection.INSUFFICIENT_DATA
    primary_conflict = any(conflict.primary_conflict for conflict in conflicts)
    if (
        configuration.neutralize_on_primary_conflict
        and primary_conflict
        and conflict_severity in {
            MarketConflictSeverity.HIGH,
            MarketConflictSeverity.CRITICAL,
        }
    ):
        return MarketDirection.CONFLICTED
    aligned_primary = any(
        item.primary
        and item.direction
        is (EvidenceDirection.BULLISH if net_score > 0 else EvidenceDirection.BEARISH)
        for item in evidence
    )
    if net_score >= configuration.strong_direction_score and aligned_primary:
        return MarketDirection.STRONGLY_BULLISH
    if net_score >= configuration.minimum_direction_score:
        return MarketDirection.BULLISH
    if net_score <= -configuration.strong_direction_score and aligned_primary:
        return MarketDirection.STRONGLY_BEARISH
    if net_score <= -configuration.minimum_direction_score:
        return MarketDirection.BEARISH
    if conflicts:
        return MarketDirection.CONFLICTED
    return MarketDirection.NEUTRAL


def _regime(
    direction: MarketDirection,
    evidence: tuple[MarketEvidence, ...],
    conflict_severity: MarketConflictSeverity,
    readiness: MarketContextReadiness,
) -> MarketRegime:
    if readiness is MarketContextReadiness.INSUFFICIENT:
        return MarketRegime.INSUFFICIENT_DATA
    if conflict_severity in {
        MarketConflictSeverity.HIGH,
        MarketConflictSeverity.CRITICAL,
    }:
        return MarketRegime.HIGH_CONFLICT
    price_action = evidence[0]
    camarilla = evidence[2]
    cpr = evidence[3]
    option_chain = evidence[1]
    if direction in {MarketDirection.STRONGLY_BULLISH, MarketDirection.BULLISH}:
        if price_action.direction is EvidenceDirection.BULLISH:
            return MarketRegime.TRENDING_UP
        if camarilla.direction is EvidenceDirection.BULLISH:
            return MarketRegime.BREAKOUT_ATTEMPT
    if direction in {MarketDirection.STRONGLY_BEARISH, MarketDirection.BEARISH}:
        if price_action.direction is EvidenceDirection.BEARISH:
            return MarketRegime.TRENDING_DOWN
        if camarilla.direction is EvidenceDirection.BEARISH:
            return MarketRegime.BREAKDOWN_ATTEMPT
    if (
        price_action.direction is EvidenceDirection.NEUTRAL
        and camarilla.direction is EvidenceDirection.NEUTRAL
        and cpr.direction is EvidenceDirection.NEUTRAL
    ):
        return MarketRegime.RANGE_BOUND
    if option_chain.direction in {EvidenceDirection.BULLISH, EvidenceDirection.BEARISH} and (
        price_action.direction not in {EvidenceDirection.UNAVAILABLE, option_chain.direction}
    ):
        return MarketRegime.REVERSAL_RISK
    return MarketRegime.RANGE_BOUND


def _posture(
    direction: MarketDirection,
    readiness: MarketContextReadiness,
    conflict_severity: MarketConflictSeverity,
) -> TradePosture:
    if readiness is MarketContextReadiness.INSUFFICIENT:
        return TradePosture.INSUFFICIENT_DATA
    if readiness is MarketContextReadiness.PARTIAL:
        return TradePosture.WAIT_FOR_CONFIRMATION
    if direction is MarketDirection.CONFLICTED or conflict_severity in {
        MarketConflictSeverity.HIGH,
        MarketConflictSeverity.CRITICAL,
    }:
        return TradePosture.AVOID_NEW_TRADES
    if direction in {MarketDirection.STRONGLY_BULLISH, MarketDirection.BULLISH}:
        return TradePosture.LOOK_FOR_LONGS
    if direction in {MarketDirection.STRONGLY_BEARISH, MarketDirection.BEARISH}:
        return TradePosture.LOOK_FOR_SHORTS
    return TradePosture.WAIT_FOR_CONFIRMATION


def _confidence(
    evidence: tuple[MarketEvidence, ...],
    net_score: int,
    readiness: MarketContextReadiness,
    conflict_severity: MarketConflictSeverity,
    primary_conflict: bool,
) -> float:
    if readiness is MarketContextReadiness.INSUFFICIENT:
        return 0.0
    maximum = sum(item.weight * 3 for item in evidence if item.available)
    if maximum <= 0:
        return 0.0
    confidence = abs(net_score) / maximum
    if conflict_severity is MarketConflictSeverity.LOW:
        confidence -= 0.05
    elif conflict_severity is MarketConflictSeverity.MODERATE:
        confidence -= 0.15
    elif conflict_severity is MarketConflictSeverity.HIGH:
        confidence -= 0.30
    elif conflict_severity is MarketConflictSeverity.CRITICAL:
        confidence = min(confidence, 0.25)
    if readiness is MarketContextReadiness.PARTIAL:
        confidence *= 0.70
    if primary_conflict:
        confidence = min(confidence, 0.35)
    return max(0.0, min(1.0, confidence))


def _rationale(
    evidence: tuple[MarketEvidence, ...],
    conflicts: tuple[MarketEvidenceConflict, ...],
    direction: MarketDirection,
    readiness: MarketContextReadiness,
) -> tuple[str, ...]:
    lines: list[str] = []
    for item in evidence:
        lines.extend(item.reasons)
    if conflicts:
        lines.append("Market evidence contains directional conflicts.")
        if any(conflict.primary_conflict for conflict in conflicts):
            lines.append("Price Action and Option Chain evidence are conflicting.")
    lines.append(
        f"Market context is {direction.value.replace('_', ' ')} "
        f"with {readiness.value} readiness."
    )
    return tuple(dict.fromkeys(lines))


def _warnings(
    evidence: tuple[MarketEvidence, ...],
    conflicts: tuple[MarketEvidenceConflict, ...],
    readiness: MarketContextReadiness,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if evidence[0].direction is EvidenceDirection.UNAVAILABLE:
        warnings.append("Price-action context is unavailable.")
    if evidence[1].direction is EvidenceDirection.UNAVAILABLE:
        warnings.append("Option-chain analytics are unavailable.")
    if any(conflict.primary_conflict for conflict in conflicts):
        warnings.append("Primary evidence is conflicting.")
    if readiness is MarketContextReadiness.PARTIAL:
        warnings.append("Only one primary source is available.")
    for item in evidence:
        for reason in item.reasons:
            if "extended above Camarilla H5" in reason:
                warnings.append("Price is extended above Camarilla H5.")
            if "extended below Camarilla L5" in reason:
                warnings.append("Price is extended below Camarilla L5.")
    return tuple(dict.fromkeys(warnings))
