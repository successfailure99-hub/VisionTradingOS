from datetime import UTC, datetime, timedelta

from application.enums import RuntimeInstrument  # noqa: F401
from engines.expert_setup_classification.enums import ExpertSetup, SetupQuality, SetupStability
from engines.market_state.enums import MarketEvidenceQuality, MarketStability, MarketState
from engines.multi_timeframe_evidence_fusion.enums import EvidenceCompleteness, EvidenceConflict, FusionDirection
from tests.test_ai_reasoning_v2_models import explanation, fusion, market_state, setup, snapshot
from engines.ai_reasoning_v2 import (
    AIConviction,
    AIReasoningChange,
    AIReasoningDirection,
    AIReasoningState,
    AIReasoningV2Configuration,
    AIReasoningV2Input,
    AIReasoningV2Interpreter,
)


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def intelligence(
    *,
    direction=FusionDirection.BULLISH,
    alignment=92.0,
    conflict_score=4.0,
    evidence_conflict=EvidenceConflict.NONE,
    completeness=EvidenceCompleteness.COMPLETE,
    state=MarketState.TRENDING,
    stability=MarketStability.STABLE,
    quality=SetupQuality.HIGH,
    setup_type=ExpertSetup.TREND_CONTINUATION,
    setup_stability=SetupStability.STABLE,
    evidence_quality=MarketEvidenceQuality.HIGH,
    minute=0,
):
    timestamp = NOW + timedelta(minutes=minute)
    return AIReasoningV2Input(
        multi_timeframe_evidence=fusion(
            timestamp=timestamp,
            direction=direction,
            alignment_score=alignment,
            conflict_score=conflict_score,
            evidence_conflict=evidence_conflict,
            completeness=completeness,
        ),
        market_state=market_state(
            timestamp=timestamp,
            state=state,
            stability=stability,
            evidence_quality=evidence_quality,
        ),
        setup_classification=setup(
            timestamp=timestamp,
            primary_setup=setup_type,
            quality=quality,
            stability=setup_stability,
        ),
        chart_explanation=explanation(timestamp=timestamp, quality=quality),
    )


def test_direction_conviction_and_state_mapping():
    interpreter = AIReasoningV2Interpreter()
    config = AIReasoningV2Configuration()

    assert interpreter.direction(intelligence(direction=FusionDirection.BULLISH)) is AIReasoningDirection.BULLISH
    assert interpreter.direction(intelligence(direction=FusionDirection.BEARISH)) is AIReasoningDirection.BEARISH
    assert interpreter.direction(intelligence(direction=FusionDirection.NEUTRAL)) is AIReasoningDirection.NEUTRAL
    assert interpreter.direction(intelligence(evidence_conflict=EvidenceConflict.MAJOR)) is AIReasoningDirection.CONFLICTED
    assert interpreter.direction(intelligence(completeness=EvidenceCompleteness.INSUFFICIENT)) is AIReasoningDirection.INSUFFICIENT_DATA
    assert interpreter.conviction(intelligence(alignment=100, conflict_score=0), config) is AIConviction.VERY_HIGH
    assert interpreter.conviction(intelligence(alignment=80, conflict_score=10), config) is AIConviction.HIGH
    assert interpreter.conviction(intelligence(alignment=50, conflict_score=20), config) is AIConviction.MODERATE
    assert interpreter.conviction(intelligence(alignment=20, conflict_score=70, quality=SetupQuality.LOW), config) is AIConviction.VERY_LOW
    assert interpreter.conviction(intelligence(completeness=EvidenceCompleteness.INSUFFICIENT), config) is AIConviction.UNAVAILABLE
    assert interpreter.reasoning_state(intelligence()) is AIReasoningState.ACTIONABLE_CONTEXT
    assert interpreter.reasoning_state(intelligence(stability=MarketStability.CHANGING)) is AIReasoningState.WAITING_CONFIRMATION
    assert interpreter.reasoning_state(intelligence(evidence_conflict=EvidenceConflict.MAJOR)) is AIReasoningState.CONFLICTED_CONTEXT
    assert interpreter.reasoning_state(intelligence(quality=SetupQuality.LOW)) is AIReasoningState.AVOID_CONTEXT


def test_evidence_roles_and_change_classification():
    interpreter = AIReasoningV2Interpreter()
    config = AIReasoningV2Configuration()
    evidence = interpreter.interpret_evidence(intelligence(), config)

    assert evidence[0].role.value == "primary"
    assert evidence[1].source == "market_state"
    assert evidence[2].role.value == "confirmation"
    assert interpreter.change_type(intelligence(), None, config) is AIReasoningChange.INITIAL
    previous = snapshot(direction=AIReasoningDirection.NEUTRAL, confidence=0.4)
    assert interpreter.change_type(intelligence(direction=FusionDirection.BULLISH), previous, config) is AIReasoningChange.TURNED_BULLISH
