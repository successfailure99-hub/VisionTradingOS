from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from application.enums import RuntimeInstrument
from core.enums.instrument import Instrument
from engines.ai_reasoning_v2.enums import (
    AICautionSeverity,
    AIConviction,
    AIReasoningChange,
    AIReasoningDirection,
    AIReasoningEvidenceRole,
    AIReasoningImpact,
    AIReasoningState,
)
from engines.ai_reasoning_v2.models import (
    AIReasoningCaution,
    AIReasoningEvidence,
    AIReasoningV2Input,
    AIReasoningV2Snapshot,
    AIWatchCondition,
)
from engines.chart_explanation.enums import ExplanationQuality
from engines.chart_explanation.models import ChartExplanationSnapshot
from engines.expert_setup_classification.enums import ExpertSetup, SetupQuality, SetupStability, SetupStrength
from engines.expert_setup_classification.models import ExpertSetupClassificationSnapshot
from engines.market_state.enums import (
    MarketEvidenceQuality,
    MarketPhase,
    MarketStability,
    MarketState,
    StructuralConfidence,
    VolatilityState,
)
from engines.market_state.models import MarketStateSnapshot
from engines.multi_timeframe_evidence_fusion.enums import (
    EvidenceAgreement,
    EvidenceCompleteness,
    EvidenceConflict,
    FusionDirection,
)
from engines.multi_timeframe_evidence_fusion.models import (
    MultiTimeframeEvidenceSnapshot,
    TimeframeEvidenceSummary,
)


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def fusion(
    *,
    instrument=RuntimeInstrument.NIFTY,
    timestamp=NOW,
    direction=FusionDirection.BULLISH,
    alignment_score=100.0,
    conflict_score=0.0,
    evidence_conflict=EvidenceConflict.NONE,
    completeness=EvidenceCompleteness.COMPLETE,
    source_fingerprint="fusion",
) -> MultiTimeframeEvidenceSnapshot:
    summary = TimeframeEvidenceSummary(
        timeframe="1m",
        direction=direction,
        completeness=completeness,
        missing_evidence=(),
        invalid_evidence=(),
        stale_evidence=(),
        timestamp=timestamp,
        source_fingerprint=f"{source_fingerprint}-summary",
    )
    return MultiTimeframeEvidenceSnapshot(
        trading_date=timestamp.date(),
        instrument=instrument,
        timeframes=("1m",),
        evidence_agreement=EvidenceAgreement.FULL_ALIGNMENT if completeness is EvidenceCompleteness.COMPLETE else EvidenceAgreement.PARTIAL_ALIGNMENT,
        evidence_conflict=evidence_conflict,
        dominant_timeframe="1m",
        alignment_score=alignment_score,
        conflict_score=conflict_score,
        evidence_completeness=completeness,
        timestamp=timestamp,
        summaries=(summary,),
        available_timeframes=("1m",) if completeness is EvidenceCompleteness.COMPLETE else (),
        missing_timeframes=() if completeness is EvidenceCompleteness.COMPLETE else ("5m",),
        invalid_timeframes=(),
        stale_timeframes=(),
        aligned_timeframes=("1m",) if evidence_conflict is EvidenceConflict.NONE else (),
        conflicting_timeframes=("15m",) if evidence_conflict is EvidenceConflict.MAJOR else (),
        weak_timeframes=(),
        source_fingerprint=source_fingerprint,
    )


def market_state(
    *,
    instrument=RuntimeInstrument.NIFTY,
    timestamp=NOW,
    state=MarketState.TRENDING,
    stability=MarketStability.STABLE,
    evidence_quality=MarketEvidenceQuality.HIGH,
    source_fingerprint="market-state",
) -> MarketStateSnapshot:
    return MarketStateSnapshot(
        trading_date=timestamp.date(),
        instrument=instrument,
        market_state=state,
        market_phase=MarketPhase.DEVELOPING,
        market_stability=stability,
        volatility_state=VolatilityState.NORMAL,
        evidence_quality=evidence_quality,
        confidence_level=StructuralConfidence.HIGH_STRUCTURE,
        dominant_timeframe="1m",
        timestamp=timestamp,
        source_fingerprint=source_fingerprint,
    )


def setup(
    *,
    instrument=RuntimeInstrument.NIFTY,
    timestamp=NOW,
    primary_setup=ExpertSetup.TREND_CONTINUATION,
    quality=SetupQuality.HIGH,
    stability=SetupStability.STABLE,
    source_fingerprint="setup",
) -> ExpertSetupClassificationSnapshot:
    return ExpertSetupClassificationSnapshot(
        trading_date=timestamp.date(),
        instrument=instrument,
        primary_setup=primary_setup,
        secondary_setup=ExpertSetup.TREND_DAY,
        setup_strength=SetupStrength.STRONG,
        setup_quality=quality,
        setup_stability=stability,
        supporting_evidence=("fusion aligned",),
        conflicting_evidence=(),
        timestamp=timestamp,
        source_fingerprint=source_fingerprint,
    )


def explanation(
    *,
    instrument=RuntimeInstrument.NIFTY,
    timestamp=NOW,
    quality=ExplanationQuality.HIGH,
    source_fingerprint="explanation",
) -> ChartExplanationSnapshot:
    if isinstance(quality, SetupQuality):
        quality = {
            SetupQuality.HIGH: ExplanationQuality.HIGH,
            SetupQuality.MEDIUM: ExplanationQuality.MEDIUM,
            SetupQuality.LOW: ExplanationQuality.LOW,
        }[quality]
    return ChartExplanationSnapshot(
        trading_date=timestamp.date(),
        instrument=instrument,
        headline="Trend Continuation",
        market_summary="The deterministic intelligence describes a trending market.",
        primary_setup_explanation="Trend continuation is supported by the current setup.",
        supporting_evidence=("fusion aligned",),
        conflicting_evidence=(),
        risk_notes=("No deterministic risk note.",),
        explanation_quality=quality,
        timestamp=timestamp,
        source_fingerprint=source_fingerprint,
    )


def ai_evidence() -> AIReasoningEvidence:
    return AIReasoningEvidence(
        source="chart_explanation",
        role=AIReasoningEvidenceRole.PRIMARY,
        impact=AIReasoningImpact.SUPPORTS_BULLISH,
        direction="bullish",
        strength="strong",
        score=2,
        explanation="Chart explanation supports the deterministic thesis.",
    )


def ai_input(**overrides) -> AIReasoningV2Input:
    data = {
        "multi_timeframe_evidence": fusion(),
        "market_state": market_state(),
        "setup_classification": setup(),
        "chart_explanation": explanation(),
        "previous_reasoning": None,
    }
    data.update(overrides)
    return AIReasoningV2Input(**data)


def snapshot(**overrides) -> AIReasoningV2Snapshot:
    data = {
        "trading_date": NOW.date(),
        "instrument": Instrument.NIFTY,
        "timestamp": NOW,
        "direction": AIReasoningDirection.BULLISH,
        "conviction": AIConviction.HIGH,
        "reasoning_state": AIReasoningState.ACTIONABLE_CONTEXT,
        "change": AIReasoningChange.INITIAL,
        "caution_severity": AICautionSeverity.NONE,
        "multi_timeframe_evidence": fusion(),
        "market_state": market_state(),
        "setup_classification": setup(),
        "chart_explanation": explanation(),
        "headline": "Trend Continuation",
        "summary": "The deterministic intelligence is aligned.",
        "primary_thesis": "The explanation and setup describe trend continuation.",
        "evidence": (ai_evidence(),),
        "supporting_points": ("chart explanation",),
        "conflicting_points": (),
        "cautions": (),
        "watch_conditions": (AIWatchCondition(1, "Watch deterministic intelligence.", "Stable context."),),
        "confidence": 0.73,
        "actionable_context": False,
        "previous_direction": None,
        "previous_confidence": None,
        "rationale": ("deterministic input contract",),
        "source_fingerprint": "ai-v2",
    }
    data.update(overrides)
    return AIReasoningV2Snapshot(**data)


def test_valid_deterministic_input_contract():
    result = ai_input()

    assert result.multi_timeframe_evidence.instrument is RuntimeInstrument.NIFTY
    assert result.market_state.instrument is RuntimeInstrument.NIFTY
    assert result.setup_classification.instrument is RuntimeInstrument.NIFTY
    assert result.chart_explanation.instrument is RuntimeInstrument.NIFTY


@pytest.mark.parametrize(
    "field",
    (
        "multi_timeframe_evidence",
        "market_state",
        "setup_classification",
        "chart_explanation",
    ),
)
def test_missing_required_deterministic_inputs_are_rejected(field):
    with pytest.raises(TypeError):
        ai_input(**{field: None})


def test_mixed_instruments_are_rejected():
    with pytest.raises(ValueError):
        ai_input(market_state=market_state(instrument=RuntimeInstrument.BANKNIFTY))


def test_timestamp_mismatch_is_rejected():
    later = datetime(2026, 7, 14, 9, 16, tzinfo=UTC)

    with pytest.raises(ValueError):
        ai_input(chart_explanation=explanation(timestamp=later))


def test_timezone_validation_is_enforced():
    naive = datetime(2026, 7, 14, 9, 15)

    with pytest.raises(ValueError):
        fusion(timestamp=naive)


def test_snapshot_contains_deterministic_intelligence_and_no_market_context_contract():
    result = snapshot()
    fields = set(AIReasoningV2Snapshot.__dataclass_fields__)

    assert result.multi_timeframe_evidence.source_fingerprint == "fusion"
    assert result.market_state.source_fingerprint == "market-state"
    assert result.setup_classification.source_fingerprint == "setup"
    assert result.chart_explanation.source_fingerprint == "explanation"
    assert "market_context" not in fields


def test_snapshot_rejects_mismatched_intelligence_timestamp():
    later = datetime(2026, 7, 14, 9, 16, tzinfo=UTC)

    with pytest.raises(ValueError):
        snapshot(chart_explanation=explanation(timestamp=later))


def test_snapshot_rejects_mismatched_instrument():
    with pytest.raises(ValueError):
        snapshot(market_state=market_state(instrument=RuntimeInstrument.BANKNIFTY))


def test_models_are_frozen_and_slotted():
    result = snapshot()

    assert hasattr(AIReasoningV2Snapshot, "__slots__")
    assert hasattr(AIReasoningV2Input, "__slots__")
    with pytest.raises(FrozenInstanceError):
        result.headline = "changed"


def test_equality_semantics_are_deterministic():
    assert snapshot() == snapshot()
    assert snapshot(source_fingerprint="left") != snapshot(source_fingerprint="right")


def test_previous_reasoning_must_match_instrument():
    previous = snapshot()
    assert ai_input(previous_reasoning=previous).previous_reasoning == previous

    with pytest.raises(ValueError):
        ai_input(previous_reasoning=snapshot(instrument=Instrument.BANKNIFTY))


def test_market_context_v2_is_not_part_of_input_contract():
    fields = set(AIReasoningV2Input.__dataclass_fields__)

    assert fields == {
        "multi_timeframe_evidence",
        "market_state",
        "setup_classification",
        "chart_explanation",
        "previous_reasoning",
    }
