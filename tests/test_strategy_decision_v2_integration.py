from dataclasses import replace
from datetime import date

from application.bootstrap import ApplicationBootstrap
from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.ai_reasoning_v2 import AIReasoningV2Engine
from engines.ai_reasoning_v2.enums import AIReasoningState
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.strategy_decision_v2 import StrategyAction, StrategyDecisionV2Engine, StrategyDecisionV2Input, StrategySetupStatus
from engines.vwap.levels import VWAPLevels
from tests.test_ai_reasoning_v2_models import (
    NOW,
    EvidenceCompleteness,
    EvidenceConflict,
    ExpertSetup,
    ExplanationQuality,
    FusionDirection,
    MarketEvidenceQuality,
    SetupQuality,
    explanation,
    fusion,
    market_state,
    setup,
)


def cam():
    return CamarillaLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 103.0, 106.0, 112.0, 118.0, 97.0, 94.0, 88.0, 82.0)


def cpr():
    return CPRLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 99.0, 101.0, 2.0, 2.0)


def vwap(instrument=Instrument.NIFTY):
    return VWAPLevels(instrument, date(2026, 7, 14), NOW, 100.0, 1000, 100000.0)


def build_stack(kind="bullish", *, timestamp=NOW):
    direction = FusionDirection.BULLISH
    conflict = EvidenceConflict.NONE
    completeness = EvidenceCompleteness.COMPLETE
    setup_kind = ExpertSetup.TREND_CONTINUATION
    setup_quality = SetupQuality.HIGH
    evidence_quality = MarketEvidenceQuality.HIGH
    explanation_quality = ExplanationQuality.HIGH

    if kind == "bearish":
        direction = FusionDirection.BEARISH
    elif kind == "conflict":
        direction = FusionDirection.MIXED
        conflict = EvidenceConflict.MAJOR
    elif kind == "insufficient":
        direction = FusionDirection.UNKNOWN
        completeness = EvidenceCompleteness.INSUFFICIENT
        evidence_quality = MarketEvidenceQuality.INSUFFICIENT
    elif kind == "low_confidence":
        setup_quality = SetupQuality.MEDIUM
        explanation_quality = ExplanationQuality.MEDIUM

    reasoning = AIReasoningV2Engine(instrument=Instrument.NIFTY).process(
        fusion(timestamp=timestamp, direction=direction, evidence_conflict=conflict, completeness=completeness),
        market_state(timestamp=timestamp, evidence_quality=evidence_quality),
        setup(timestamp=timestamp, primary_setup=setup_kind, quality=setup_quality),
        explanation(timestamp=timestamp, quality=explanation_quality),
        timestamp=timestamp,
    )
    if kind == "low_confidence":
        reasoning = replace(reasoning, confidence=0.2)
    return reasoning


def replace_context(reasoning, **changes):
    timestamp = changes.pop("timestamp", reasoning.timestamp)
    confidence = changes.pop("confidence", reasoning.confidence)
    state = changes.pop("reasoning_state", reasoning.reasoning_state)
    primary_setup = changes.pop("primary_setup", reasoning.setup_classification.primary_setup)
    setup_quality = changes.pop("setup_quality", reasoning.setup_classification.setup_quality)
    direction = changes.pop("direction", reasoning.multi_timeframe_evidence.summaries[0].direction)
    conflict = changes.pop("evidence_conflict", reasoning.multi_timeframe_evidence.evidence_conflict)
    completeness = changes.pop("evidence_completeness", reasoning.multi_timeframe_evidence.evidence_completeness)
    if changes:
        raise TypeError(f"unsupported deterministic intelligence changes: {tuple(sorted(changes))}")

    updated = AIReasoningV2Engine(instrument=Instrument.NIFTY).process(
        fusion(timestamp=timestamp, direction=direction, evidence_conflict=conflict, completeness=completeness),
        market_state(timestamp=timestamp),
        setup(timestamp=timestamp, primary_setup=primary_setup, quality=setup_quality),
        explanation(timestamp=timestamp),
        timestamp=timestamp,
    )
    return replace(
        updated,
        confidence=confidence,
        reasoning_state=state,
        actionable_context=state is AIReasoningState.ACTIONABLE_CONTEXT,
    )


def test_replace_context_keeps_reasoning_and_intelligence_timestamps_aligned():
    reasoning = build_stack("bullish")
    new_timestamp = reasoning.timestamp.replace(minute=reasoning.timestamp.minute + 1)

    updated = replace_context(
        reasoning,
        timestamp=new_timestamp,
    )

    assert updated.timestamp == new_timestamp
    assert updated.multi_timeframe_evidence.timestamp == new_timestamp
    assert updated.market_state.timestamp == new_timestamp
    assert updated.setup_classification.timestamp == new_timestamp
    assert updated.chart_explanation.timestamp == new_timestamp
    assert updated.instrument is Instrument.NIFTY


def test_no_network_strategy_decision_flow_and_application_defaults():
    engine = StrategyDecisionV2Engine(instrument=Instrument.NIFTY)
    bullish = engine.process(StrategyDecisionV2Input(build_stack("bullish")))
    assert bullish.action is StrategyAction.CONSIDER_LONG
    assert bullish.setup_status is StrategySetupStatus.READY_FOR_RISK_REVIEW
    assert bullish.risk_handoff.requires_risk_review is True
    assert bullish.ai_reasoning.setup_classification.primary_setup is ExpertSetup.TREND_CONTINUATION
    bearish = engine.process(StrategyDecisionV2Input(build_stack("bearish")))
    assert bearish.action is StrategyAction.CONSIDER_SHORT
    conflict = StrategyDecisionV2Engine(instrument=Instrument.NIFTY).process(StrategyDecisionV2Input(build_stack("conflict")))
    assert conflict.action is StrategyAction.NO_TRADE
    lifecycle = ApplicationBootstrap().create_application()
    snapshot = lifecycle.snapshot().orchestrator_snapshot
    assert snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert snapshot.broker_mode is BrokerExecutionMode.DRY_RUN
