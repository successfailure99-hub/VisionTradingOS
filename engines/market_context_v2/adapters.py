"""
Pure evidence adapters for Market Context Engine V2.
"""

from datetime import datetime

from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context_v2.enums import (
    EvidenceDirection,
    EvidenceStrength,
    MarketEvidenceSource,
)
from engines.market_context_v2.models import MarketEvidence
from engines.option_chain_analytics.enums import OptionAnalyticsBias
from engines.option_chain_analytics.models import OptionChainAnalyticsSnapshot
from engines.price_action.enums import BreakType, StructureType, Trend
from engines.price_action.models import PriceActionState
from engines.vwap.levels import VWAPLevels


_MULTIPLIER = {
    EvidenceStrength.WEAK: 1,
    EvidenceStrength.MODERATE: 2,
    EvidenceStrength.STRONG: 3,
}


def price_action_evidence(
    snapshot: PriceActionState | None,
    *,
    timestamp: datetime,
    weight: int,
) -> MarketEvidence:
    if snapshot is None:
        return _evidence(
            MarketEvidenceSource.PRICE_ACTION,
            EvidenceDirection.UNAVAILABLE,
            EvidenceStrength.WEAK,
            weight,
            timestamp,
            ("Price-action context is unavailable.",),
            available=False,
        )

    bullish_parts = 0
    bearish_parts = 0
    for point in (snapshot.latest_swing_high, snapshot.latest_swing_low):
        if point is None:
            continue
        if point.structure_type in {
            StructureType.HIGHER_HIGH,
            StructureType.HIGHER_LOW,
        }:
            bullish_parts += 1
        if point.structure_type in {
            StructureType.LOWER_HIGH,
            StructureType.LOWER_LOW,
        }:
            bearish_parts += 1
    latest_break = snapshot.latest_break.break_type if snapshot.latest_break else None
    if latest_break in {BreakType.BULLISH_BOS, BreakType.BULLISH_CHOCH}:
        bullish_parts += 1
    if latest_break in {BreakType.BEARISH_BOS, BreakType.BEARISH_CHOCH}:
        bearish_parts += 1

    if snapshot.trend is Trend.BULLISH and bearish_parts == 0:
        strength = EvidenceStrength.STRONG if bullish_parts >= 2 else EvidenceStrength.MODERATE
        return _evidence(
            MarketEvidenceSource.PRICE_ACTION,
            EvidenceDirection.BULLISH,
            strength,
            weight,
            timestamp,
            ("Price action shows a bullish market structure.",),
        )
    if snapshot.trend is Trend.BEARISH and bullish_parts == 0:
        strength = EvidenceStrength.STRONG if bearish_parts >= 2 else EvidenceStrength.MODERATE
        return _evidence(
            MarketEvidenceSource.PRICE_ACTION,
            EvidenceDirection.BEARISH,
            strength,
            weight,
            timestamp,
            ("Price action shows a bearish market structure.",),
        )
    if bullish_parts > 0 and bearish_parts > 0:
        return _evidence(
            MarketEvidenceSource.PRICE_ACTION,
            EvidenceDirection.CONFLICTED,
            EvidenceStrength.STRONG,
            weight,
            timestamp,
            ("Price action structure is mixed.",),
        )
    if snapshot.trend is Trend.RANGE:
        reason = "Price action shows a range-bound market structure."
    else:
        reason = "Price action has no confirmed directional structure."
    return _evidence(
        MarketEvidenceSource.PRICE_ACTION,
        EvidenceDirection.NEUTRAL,
        EvidenceStrength.MODERATE,
        weight,
        timestamp,
        (reason,),
    )


def option_chain_evidence(
    snapshot: OptionChainAnalyticsSnapshot | None,
    *,
    timestamp: datetime,
    weight: int,
) -> MarketEvidence:
    if snapshot is None or snapshot.bias is OptionAnalyticsBias.INSUFFICIENT_DATA:
        return _evidence(
            MarketEvidenceSource.OPTION_CHAIN,
            EvidenceDirection.UNAVAILABLE,
            EvidenceStrength.WEAK,
            weight,
            timestamp,
            ("Option-chain analytics are unavailable.",),
            available=False,
        )

    mapping = {
        OptionAnalyticsBias.STRONGLY_BULLISH: (
            EvidenceDirection.BULLISH,
            EvidenceStrength.STRONG,
            "Option-chain analytics are strongly bullish.",
        ),
        OptionAnalyticsBias.BULLISH: (
            EvidenceDirection.BULLISH,
            EvidenceStrength.MODERATE,
            "Option-chain analytics are bullish.",
        ),
        OptionAnalyticsBias.NEUTRAL: (
            EvidenceDirection.NEUTRAL,
            EvidenceStrength.MODERATE,
            "Option-chain analytics are neutral.",
        ),
        OptionAnalyticsBias.BEARISH: (
            EvidenceDirection.BEARISH,
            EvidenceStrength.MODERATE,
            "Option-chain analytics are bearish.",
        ),
        OptionAnalyticsBias.STRONGLY_BEARISH: (
            EvidenceDirection.BEARISH,
            EvidenceStrength.STRONG,
            "Option-chain analytics are strongly bearish.",
        ),
        OptionAnalyticsBias.CONFLICTED: (
            EvidenceDirection.CONFLICTED,
            EvidenceStrength.STRONG,
            "Option-chain analytics are conflicting.",
        ),
    }
    direction, strength, reason = mapping[snapshot.bias]
    extra = tuple(snapshot.rationale[:2])
    return _evidence(
        MarketEvidenceSource.OPTION_CHAIN,
        direction,
        strength,
        weight,
        timestamp,
        (reason,) + extra,
    )


def camarilla_evidence(
    snapshot: CamarillaLevels | None,
    *,
    current_price: float,
    timestamp: datetime,
    weight: int,
) -> MarketEvidence:
    if snapshot is None:
        return _evidence(
            MarketEvidenceSource.CAMARILLA,
            EvidenceDirection.UNAVAILABLE,
            EvidenceStrength.WEAK,
            weight,
            timestamp,
            ("Camarilla levels are unavailable.",),
            available=False,
        )
    if current_price > snapshot.h6:
        reason = "Price is extended above Camarilla H6."
        return _evidence(MarketEvidenceSource.CAMARILLA, EvidenceDirection.BULLISH, EvidenceStrength.STRONG, weight, timestamp, (reason,))
    if current_price > snapshot.h5:
        reason = "Price is extended above Camarilla H5."
        return _evidence(MarketEvidenceSource.CAMARILLA, EvidenceDirection.BULLISH, EvidenceStrength.STRONG, weight, timestamp, (reason,))
    if current_price > snapshot.h4:
        reason = "Price is trading above Camarilla H4."
        return _evidence(MarketEvidenceSource.CAMARILLA, EvidenceDirection.BULLISH, EvidenceStrength.MODERATE, weight, timestamp, (reason,))
    if current_price > snapshot.h3:
        reason = "Price is trading between Camarilla H3 and H4."
        return _evidence(MarketEvidenceSource.CAMARILLA, EvidenceDirection.BULLISH, EvidenceStrength.WEAK, weight, timestamp, (reason,))
    if current_price < snapshot.l6:
        reason = "Price is extended below Camarilla L6."
        return _evidence(MarketEvidenceSource.CAMARILLA, EvidenceDirection.BEARISH, EvidenceStrength.STRONG, weight, timestamp, (reason,))
    if current_price < snapshot.l5:
        reason = "Price is extended below Camarilla L5."
        return _evidence(MarketEvidenceSource.CAMARILLA, EvidenceDirection.BEARISH, EvidenceStrength.STRONG, weight, timestamp, (reason,))
    if current_price < snapshot.l4:
        reason = "Price is trading below Camarilla L4."
        return _evidence(MarketEvidenceSource.CAMARILLA, EvidenceDirection.BEARISH, EvidenceStrength.MODERATE, weight, timestamp, (reason,))
    if current_price < snapshot.l3:
        reason = "Price is trading between Camarilla L4 and L3."
        return _evidence(MarketEvidenceSource.CAMARILLA, EvidenceDirection.BEARISH, EvidenceStrength.WEAK, weight, timestamp, (reason,))
    return _evidence(
        MarketEvidenceSource.CAMARILLA,
        EvidenceDirection.NEUTRAL,
        EvidenceStrength.MODERATE,
        weight,
        timestamp,
        ("Price is between Camarilla L3 and H3.",),
    )


def cpr_evidence(
    snapshot: CPRLevels | None,
    *,
    current_price: float,
    timestamp: datetime,
    weight: int,
) -> MarketEvidence:
    if snapshot is None:
        return _evidence(
            MarketEvidenceSource.CPR,
            EvidenceDirection.UNAVAILABLE,
            EvidenceStrength.WEAK,
            weight,
            timestamp,
            ("CPR levels are unavailable.",),
            available=False,
        )
    if current_price > snapshot.tc:
        return _evidence(
            MarketEvidenceSource.CPR,
            EvidenceDirection.BULLISH,
            EvidenceStrength.MODERATE,
            weight,
            timestamp,
            ("Price is above the CPR top central level.",),
        )
    if current_price < snapshot.bc:
        return _evidence(
            MarketEvidenceSource.CPR,
            EvidenceDirection.BEARISH,
            EvidenceStrength.MODERATE,
            weight,
            timestamp,
            ("Price is below the CPR bottom central level.",),
        )
    return _evidence(
        MarketEvidenceSource.CPR,
        EvidenceDirection.NEUTRAL,
        EvidenceStrength.MODERATE,
        weight,
        timestamp,
        ("Price is inside the CPR.",),
    )


def vwap_evidence(
    snapshot: VWAPLevels | None,
    *,
    current_price: float,
    timestamp: datetime,
    weight: int,
) -> MarketEvidence:
    if snapshot is None:
        return _evidence(
            MarketEvidenceSource.VWAP,
            EvidenceDirection.UNAVAILABLE,
            EvidenceStrength.WEAK,
            weight,
            timestamp,
            ("VWAP context is unavailable.",),
            available=False,
        )
    if current_price > snapshot.vwap:
        return _evidence(
            MarketEvidenceSource.VWAP,
            EvidenceDirection.BULLISH,
            EvidenceStrength.MODERATE,
            weight,
            timestamp,
            ("Price is above VWAP.",),
        )
    if current_price < snapshot.vwap:
        return _evidence(
            MarketEvidenceSource.VWAP,
            EvidenceDirection.BEARISH,
            EvidenceStrength.MODERATE,
            weight,
            timestamp,
            ("Price is below VWAP.",),
        )
    return _evidence(
        MarketEvidenceSource.VWAP,
        EvidenceDirection.NEUTRAL,
        EvidenceStrength.MODERATE,
        weight,
        timestamp,
        ("Price is equal to VWAP.",),
    )


def _evidence(
    source: MarketEvidenceSource,
    direction: EvidenceDirection,
    strength: EvidenceStrength,
    weight: int,
    timestamp: datetime,
    reasons: tuple[str, ...],
    *,
    available: bool = True,
) -> MarketEvidence:
    score = 0
    if direction is EvidenceDirection.BULLISH:
        score = weight * _MULTIPLIER[strength]
    elif direction is EvidenceDirection.BEARISH:
        score = -(weight * _MULTIPLIER[strength])
    return MarketEvidence(
        source=source,
        direction=direction,
        strength=strength,
        weight=weight,
        score=score,
        available=available,
        primary=source in {
            MarketEvidenceSource.PRICE_ACTION,
            MarketEvidenceSource.OPTION_CHAIN,
        },
        timestamp=timestamp,
        reasons=reasons,
    )
