from datetime import UTC, datetime, timedelta

from core.enums.instrument import Instrument
from engines.ai_reasoning_v2 import (
    AIConviction,
    AIReasoningChange,
    AIReasoningDirection,
    AIReasoningState,
    AIReasoningV2Configuration,
    AIReasoningV2Interpreter,
)
from engines.market_context_v2.enums import (
    EvidenceDirection,
    EvidenceStrength,
    MarketConflictSeverity,
    MarketContextReadiness,
    MarketDirection,
    MarketEvidenceSource,
    MarketRegime,
    TradePosture,
)
from engines.market_context_v2.models import MarketContextV2Snapshot, MarketEvidence


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def ev(source, direction, score, timestamp=NOW):
    return MarketEvidence(source, direction, EvidenceStrength.MODERATE, 1, score, direction is not EvidenceDirection.UNAVAILABLE, source in {MarketEvidenceSource.PRICE_ACTION, MarketEvidenceSource.OPTION_CHAIN}, timestamp, (f"{source.value} {direction.value}",))


def ctx(
    direction=MarketDirection.BULLISH,
    confidence=0.75,
    readiness=MarketContextReadiness.READY,
    posture=TradePosture.LOOK_FOR_LONGS,
    conflict=MarketConflictSeverity.NONE,
    *,
    minute=0,
):
    timestamp = NOW + timedelta(minutes=minute)
    edir = EvidenceDirection.BULLISH if direction in {MarketDirection.BULLISH, MarketDirection.STRONGLY_BULLISH} else EvidenceDirection.BEARISH if direction in {MarketDirection.BEARISH, MarketDirection.STRONGLY_BEARISH} else EvidenceDirection.NEUTRAL
    score = 2 if edir is EvidenceDirection.BULLISH else -2 if edir is EvidenceDirection.BEARISH else 0
    items = (
        ev(MarketEvidenceSource.PRICE_ACTION, edir, score, timestamp),
        ev(MarketEvidenceSource.OPTION_CHAIN, edir, score, timestamp),
        ev(MarketEvidenceSource.CAMARILLA, EvidenceDirection.NEUTRAL, 0, timestamp),
        ev(MarketEvidenceSource.CPR, EvidenceDirection.NEUTRAL, 0, timestamp),
        ev(MarketEvidenceSource.VWAP, EvidenceDirection.NEUTRAL, 0, timestamp),
    )
    bullish = 4 if score > 0 else 0
    bearish = 4 if score < 0 else 0
    return MarketContextV2Snapshot(Instrument.NIFTY, timestamp, readiness, direction, MarketRegime.TRENDING_UP, posture, conflict, bullish, bearish, bullish - bearish, confidence, items, (), items[0], items[1], items[2], items[3], items[4], 100.0, None, 2 if readiness is not MarketContextReadiness.INSUFFICIENT else 0, 3, ("context",), ())


def test_direction_conviction_and_state_mapping():
    interpreter = AIReasoningV2Interpreter()
    config = AIReasoningV2Configuration()
    assert interpreter.direction(ctx(MarketDirection.STRONGLY_BULLISH)) is AIReasoningDirection.STRONGLY_BULLISH
    assert interpreter.conviction(ctx(confidence=0.9), config) is AIConviction.VERY_HIGH
    assert interpreter.conviction(ctx(confidence=0.72), config) is AIConviction.HIGH
    assert interpreter.conviction(ctx(confidence=0.55), config) is AIConviction.MODERATE
    assert interpreter.conviction(ctx(confidence=0.35), config) is AIConviction.LOW
    assert interpreter.conviction(ctx(confidence=0.1), config) is AIConviction.VERY_LOW
    assert interpreter.conviction(ctx(readiness=MarketContextReadiness.INSUFFICIENT, confidence=0.0), config) is AIConviction.UNAVAILABLE
    assert interpreter.conviction(ctx(conflict=MarketConflictSeverity.HIGH), config) is AIConviction.LOW
    assert interpreter.reasoning_state(ctx()) is AIReasoningState.ACTIONABLE_CONTEXT
    assert interpreter.reasoning_state(ctx(posture=TradePosture.WAIT_FOR_CONFIRMATION)) is AIReasoningState.WAITING_CONFIRMATION
    assert interpreter.reasoning_state(ctx(direction=MarketDirection.CONFLICTED, conflict=MarketConflictSeverity.HIGH, posture=TradePosture.AVOID_NEW_TRADES)) is AIReasoningState.CONFLICTED_CONTEXT


def test_evidence_roles_and_initial_change():
    interpreter = AIReasoningV2Interpreter()
    evidence = interpreter.interpret_evidence(ctx(), AIReasoningV2Configuration())
    assert evidence[0].role.value == "primary"
    assert evidence[2].role.value == "confirmation"
    assert interpreter.change_type(ctx(), None) is AIReasoningChange.INITIAL
