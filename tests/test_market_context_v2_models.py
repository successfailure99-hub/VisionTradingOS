from datetime import UTC, datetime

import pytest

from core.enums.instrument import Instrument
from engines.market_context_v2 import (
    EvidenceDirection,
    EvidenceStrength,
    MarketConflictSeverity,
    MarketContextReadiness,
    MarketDirection,
    MarketEvidence,
    MarketEvidenceConflict,
    MarketEvidenceSource,
    MarketRegime,
    TradePosture,
)
from engines.market_context_v2.models import MarketContextV2Snapshot


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def evidence(source, direction, score, available=True):
    return MarketEvidence(
        source=source,
        direction=direction,
        strength=EvidenceStrength.MODERATE,
        weight=1,
        score=score,
        available=available,
        primary=source
        in {MarketEvidenceSource.PRICE_ACTION, MarketEvidenceSource.OPTION_CHAIN},
        timestamp=NOW,
        reasons=(f"{source.value} reason",),
    )


def snapshot():
    items = (
        evidence(MarketEvidenceSource.PRICE_ACTION, EvidenceDirection.BULLISH, 2),
        evidence(MarketEvidenceSource.OPTION_CHAIN, EvidenceDirection.BULLISH, 2),
        evidence(MarketEvidenceSource.CAMARILLA, EvidenceDirection.NEUTRAL, 0),
        evidence(MarketEvidenceSource.CPR, EvidenceDirection.NEUTRAL, 0),
        evidence(MarketEvidenceSource.VWAP, EvidenceDirection.NEUTRAL, 0),
    )
    return MarketContextV2Snapshot(
        instrument=Instrument.NIFTY,
        timestamp=NOW,
        readiness=MarketContextReadiness.READY,
        direction=MarketDirection.BULLISH,
        regime=MarketRegime.TRENDING_UP,
        trade_posture=TradePosture.LOOK_FOR_LONGS,
        conflict_severity=MarketConflictSeverity.NONE,
        bullish_score=4,
        bearish_score=0,
        net_score=4,
        confidence=0.7,
        evidence=items,
        conflicts=(),
        price_action_evidence=items[0],
        option_chain_evidence=items[1],
        camarilla_evidence=items[2],
        cpr_evidence=items[3],
        vwap_evidence=items[4],
        current_price=100.0,
        reference_vwap=None,
        primary_sources_available=2,
        secondary_sources_available=3,
        rationale=("Market context is bullish.",),
        warnings=(),
    )


def test_frozen_slotted_valid_evidence_and_snapshot():
    item = evidence(MarketEvidenceSource.PRICE_ACTION, EvidenceDirection.BULLISH, 2)
    assert hasattr(MarketEvidence, "__slots__")
    with pytest.raises(Exception):
        item.score = 0
    result = snapshot()
    assert result.net_score == result.bullish_score - result.bearish_score
    assert isinstance(result.evidence, tuple)
    assert result.evidence[0] is result.price_action_evidence


def test_invalid_evidence_rules():
    with pytest.raises(ValueError):
        evidence(MarketEvidenceSource.PRICE_ACTION, EvidenceDirection.BULLISH, 0)
    with pytest.raises(ValueError):
        evidence(MarketEvidenceSource.PRICE_ACTION, EvidenceDirection.BEARISH, 1)
    with pytest.raises(ValueError):
        evidence(MarketEvidenceSource.PRICE_ACTION, EvidenceDirection.UNAVAILABLE, 0, True)
    with pytest.raises(ValueError):
        MarketEvidence(
            source=MarketEvidenceSource.CPR,
            direction=EvidenceDirection.UNAVAILABLE,
            strength=EvidenceStrength.WEAK,
            weight=1,
            score=0,
            available=False,
            primary=True,
            timestamp=NOW,
            reasons=("bad",),
        )


@pytest.mark.parametrize(
    ("direction", "score"),
    [
        (EvidenceDirection.BULLISH, 0),
        (EvidenceDirection.BULLISH, -1),
        (EvidenceDirection.BEARISH, 0),
        (EvidenceDirection.BEARISH, 1),
        (EvidenceDirection.NEUTRAL, 1),
        (EvidenceDirection.NEUTRAL, -1),
        (EvidenceDirection.CONFLICTED, 1),
        (EvidenceDirection.CONFLICTED, -1),
        (EvidenceDirection.UNAVAILABLE, 1),
        (EvidenceDirection.UNAVAILABLE, -1),
    ],
)
def test_invalid_direction_score_combinations(direction, score):
    with pytest.raises(ValueError):
        evidence(
            MarketEvidenceSource.PRICE_ACTION,
            direction,
            score,
            available=direction is not EvidenceDirection.UNAVAILABLE,
        )


@pytest.mark.parametrize(
    "direction",
    [
        EvidenceDirection.BULLISH,
        EvidenceDirection.NEUTRAL,
    ],
)
def test_available_false_requires_unavailable_direction(direction):
    with pytest.raises(ValueError):
        evidence(
            MarketEvidenceSource.PRICE_ACTION,
            direction,
            1 if direction is EvidenceDirection.BULLISH else 0,
            available=False,
        )


def test_unavailable_direction_requires_available_false():
    with pytest.raises(ValueError):
        evidence(
            MarketEvidenceSource.PRICE_ACTION,
            EvidenceDirection.UNAVAILABLE,
            0,
            available=True,
        )


def test_secondary_source_cannot_be_primary():
    with pytest.raises(ValueError):
        MarketEvidence(
            source=MarketEvidenceSource.CAMARILLA,
            direction=EvidenceDirection.BULLISH,
            strength=EvidenceStrength.MODERATE,
            weight=1,
            score=2,
            available=True,
            primary=True,
            timestamp=NOW,
            reasons=("bad primary flag",),
        )


@pytest.mark.parametrize(
    ("direction", "score", "available"),
    [
        (EvidenceDirection.BULLISH, 1, True),
        (EvidenceDirection.BEARISH, -1, True),
        (EvidenceDirection.NEUTRAL, 0, True),
        (EvidenceDirection.CONFLICTED, 0, True),
        (EvidenceDirection.UNAVAILABLE, 0, False),
    ],
)
def test_valid_direction_score_and_availability_combinations(
    direction,
    score,
    available,
):
    item = evidence(
        MarketEvidenceSource.PRICE_ACTION,
        direction,
        score,
        available=available,
    )
    assert item.direction is direction
    assert item.score == score
    assert item.available is available


def test_conflict_and_snapshot_validation():
    conflict = MarketEvidenceConflict(
        source_a=MarketEvidenceSource.PRICE_ACTION,
        direction_a=EvidenceDirection.BULLISH,
        source_b=MarketEvidenceSource.OPTION_CHAIN,
        direction_b=EvidenceDirection.BEARISH,
        severity=MarketConflictSeverity.HIGH,
        primary_conflict=True,
        rationale="primary conflict",
    )
    assert conflict.primary_conflict is True
    with pytest.raises(ValueError):
        MarketEvidenceConflict(
            source_a=MarketEvidenceSource.CPR,
            direction_a=EvidenceDirection.NEUTRAL,
            source_b=MarketEvidenceSource.VWAP,
            direction_b=EvidenceDirection.BEARISH,
            severity=MarketConflictSeverity.LOW,
            primary_conflict=False,
            rationale="bad",
        )
    with pytest.raises(ValueError):
        bad = snapshot()
        MarketContextV2Snapshot(
            **{**{field: getattr(bad, field) for field in bad.__dataclass_fields__}, "net_score": 99}
        )
