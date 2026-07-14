from datetime import UTC, datetime

import pytest

from core.enums.instrument import Instrument
from engines.ai_reasoning_v2 import (
    AICautionSeverity,
    AIConviction,
    AIReasoningCaution,
    AIReasoningChange,
    AIReasoningDirection,
    AIReasoningEvidence,
    AIReasoningEvidenceRole,
    AIReasoningImpact,
    AIReasoningState,
    AIReasoningV2Input,
    AIReasoningV2Snapshot,
    AIWatchCondition,
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


def mc_evidence(source, direction=EvidenceDirection.BULLISH, score=1):
    return MarketEvidence(source, direction, EvidenceStrength.MODERATE, 1, score, direction is not EvidenceDirection.UNAVAILABLE, source in {MarketEvidenceSource.PRICE_ACTION, MarketEvidenceSource.OPTION_CHAIN}, NOW, (f"{source.value} reason",))


def context():
    items = (
        mc_evidence(MarketEvidenceSource.PRICE_ACTION, EvidenceDirection.BULLISH, 2),
        mc_evidence(MarketEvidenceSource.OPTION_CHAIN, EvidenceDirection.BULLISH, 2),
        mc_evidence(MarketEvidenceSource.CAMARILLA, EvidenceDirection.NEUTRAL, 0),
        mc_evidence(MarketEvidenceSource.CPR, EvidenceDirection.NEUTRAL, 0),
        mc_evidence(MarketEvidenceSource.VWAP, EvidenceDirection.NEUTRAL, 0),
    )
    return MarketContextV2Snapshot(Instrument.NIFTY, NOW, MarketContextReadiness.READY, MarketDirection.BULLISH, MarketRegime.TRENDING_UP, TradePosture.LOOK_FOR_LONGS, MarketConflictSeverity.NONE, 4, 0, 4, 0.7, items, (), items[0], items[1], items[2], items[3], items[4], 100.0, None, 2, 3, ("context",), ())


def ai_evidence(role=AIReasoningEvidenceRole.PRIMARY):
    return AIReasoningEvidence(MarketEvidenceSource.PRICE_ACTION, role, AIReasoningImpact.SUPPORTS_BULLISH, EvidenceDirection.BULLISH, EvidenceStrength.MODERATE, 2, "Price action supports bullish context.")


def snapshot():
    ctx = context()
    evidence = (ai_evidence(),)
    return AIReasoningV2Snapshot(Instrument.NIFTY, NOW, AIReasoningDirection.BULLISH, AIConviction.HIGH, AIReasoningState.ACTIONABLE_CONTEXT, AIReasoningChange.INITIAL, AICautionSeverity.NONE, ctx, "NIFTY market context is bullish.", "NIFTY has a bullish market context.", "Price Action and Option Chain Analytics are aligned bullish.", evidence, ("support",), (), (), (AIWatchCondition(1, "Wait for confirmation.", "Reason"),), ctx.confidence, True, None, None, ("rationale",))


def test_frozen_slotted_models_and_snapshot_contract():
    result = snapshot()
    assert hasattr(AIReasoningV2Snapshot, "__slots__")
    assert result.market_context is context() or result.market_context.instrument is Instrument.NIFTY
    with pytest.raises(Exception):
        result.headline = "changed"
    assert isinstance(result.supporting_points, tuple)


def test_model_validation_rules():
    with pytest.raises(ValueError):
        AIReasoningEvidence(MarketEvidenceSource.CPR, AIReasoningEvidenceRole.PRIMARY, AIReasoningImpact.SUPPORTS_BULLISH, EvidenceDirection.BULLISH, EvidenceStrength.MODERATE, 2, "bad")
    with pytest.raises(ValueError):
        AIReasoningCaution(AICautionSeverity.LOW, "", "message")
    with pytest.raises(ValueError):
        AIWatchCondition(0, "condition", "reason")
    with pytest.raises(TypeError):
        AIReasoningV2Input(context="bad")


def test_no_order_prompt_model_or_broker_fields():
    fields = set(AIReasoningV2Snapshot.__dataclass_fields__)
    forbidden = ("entry", "stop", "target", "quantity", "order", "broker", "prompt", "model")
    assert not any(any(word in name.lower() for word in forbidden) for name in fields)
