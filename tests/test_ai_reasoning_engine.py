"""
Tests for AI Reasoning Engine V1.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from core.event_bus import EventBus
from core.events import AI_DECISION_READY
from engines.ai_reasoning import (
    AgreementSummary,
    AIReasoningEngine,
    AIReasoningState,
    AIMarketSummary,
    ConflictSummary,
    ReasoningConfidence,
    TradingSuitability,
)
from engines.market_context.enums import (
    AgreementState,
    CamarillaZone,
    ContextStrength,
    CPRPosition,
    EvidenceDirection,
    MarketBias,
    MarketPhase,
    VWAPPosition,
)
from engines.market_context.models import ContextEvidence, MarketContextState


TS = datetime(2026, 7, 10, 10, 0)


def assert_raises(expected_error, callback):
    try:
        callback()
    except expected_error:
        return
    raise AssertionError(f"Expected {expected_error}")


def evidence(
    price_action=EvidenceDirection.BULLISH,
    option_chain=EvidenceDirection.BULLISH,
    vwap=EvidenceDirection.BULLISH,
    cpr=EvidenceDirection.BULLISH,
    camarilla=EvidenceDirection.NEUTRAL,
):
    return (
        ContextEvidence("price_action", price_action, "price_action_detail"),
        ContextEvidence("option_chain", option_chain, "option_chain_detail"),
        ContextEvidence("vwap", vwap, "vwap_detail"),
        ContextEvidence("cpr", cpr, "cpr_detail"),
        ContextEvidence("camarilla", camarilla, "camarilla_detail"),
    )


def context(
    symbol="NIFTY",
    timeframe="1m",
    timestamp=TS,
    market_bias=MarketBias.BULLISH,
    market_phase=MarketPhase.TRENDING_UP,
    agreement=AgreementState.ALIGNED,
    context_strength=ContextStrength.STRONG,
    price_action_direction=EvidenceDirection.BULLISH,
    option_chain_direction=EvidenceDirection.BULLISH,
    bullish_count=4,
    bearish_count=0,
    neutral_count=1,
    mixed_count=0,
    available_count=5,
    missing_sources=(),
    context_evidence=None,
):
    if context_evidence is None:
        context_evidence = evidence(
            price_action_direction,
            option_chain_direction,
            EvidenceDirection.BULLISH,
            EvidenceDirection.BULLISH,
            EvidenceDirection.NEUTRAL,
        )
    return MarketContextState(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        current_price=100,
        session_high=105,
        session_low=95,
        market_bias=market_bias,
        market_phase=market_phase,
        agreement=agreement,
        context_strength=context_strength,
        price_action_direction=price_action_direction,
        option_chain_direction=option_chain_direction,
        vwap_position=VWAPPosition.ABOVE,
        cpr_position=CPRPosition.ABOVE,
        virgin_cpr=False,
        camarilla_zone=CamarillaZone.L3_TO_H3,
        bullish_evidence_count=bullish_count,
        bearish_evidence_count=bearish_count,
        neutral_evidence_count=neutral_count,
        mixed_evidence_count=mixed_count,
        available_source_count=available_count,
        evidence=context_evidence,
        missing_sources=missing_sources,
    )


def engine(symbol=" nifty ", timeframe=" 1m "):
    return AIReasoningEngine(EventBus(), symbol, timeframe)


def feed(ai_engine, mc_context=None):
    return ai_engine.update(mc_context or context())


def assert_rejected_preserves_state(ai_engine, bad_context, expected_error=ValueError):
    old_context = ai_engine.context
    old_state = ai_engine.state
    old_data = ai_engine.data
    old_ready = ai_engine.is_ready()
    events = []
    ai_engine._event_bus.subscribe(AI_DECISION_READY, events.append)

    assert_raises(expected_error, lambda: ai_engine.update(bad_context))

    assert ai_engine.context == old_context
    assert ai_engine.state == old_state
    assert ai_engine.data == old_data
    assert ai_engine.is_ready() == old_ready
    assert events == []


def test_enum_values_models_and_exports():
    assert AIMarketSummary.BULLISH.value == "bullish"
    assert ReasoningConfidence.HIGH.value == "high"
    assert AgreementSummary.CONFLICTED.value == "conflicted"
    assert ConflictSummary.SECONDARY_CONFLICT.value == "secondary_conflict"
    assert TradingSuitability.WATCHLIST.value == "watchlist"

    state = feed(engine())
    assert_raises(FrozenInstanceError, lambda: setattr(state, "confidence", ReasoningConfidence.LOW))
    assert_raises((FrozenInstanceError, TypeError), lambda: setattr(state, "extra", 1))

    from engines.ai_reasoning import __all__

    assert __all__ == [
        "AIReasoningEngine",
        "AIReasoningCalculator",
        "AIReasoningState",
        "AIMarketSummary",
        "ReasoningConfidence",
        "AgreementSummary",
        "ConflictSummary",
        "TradingSuitability",
    ]


def test_constructor_initial_state_and_invalid_context():
    ai = engine()
    assert ai.symbol == "NIFTY"
    assert ai.timeframe == "1m"
    assert ai.context is None
    assert ai.state is None
    assert ai.data is None
    assert not ai.is_ready()
    assert_raises(ValueError, lambda: AIReasoningEngine(EventBus(), "", "1m"))
    assert_raises(ValueError, lambda: AIReasoningEngine(EventBus(), 1, "1m"))
    assert_raises(ValueError, lambda: AIReasoningEngine(EventBus(), "NIFTY", ""))
    assert_raises(ValueError, lambda: AIReasoningEngine(EventBus(), "NIFTY", 1))


def test_strong_aligned_bullish_reasoning_is_deterministic():
    result = feed(engine())
    assert isinstance(result, AIReasoningState)
    assert result.symbol == "NIFTY"
    assert result.timeframe == "1m"
    assert result.timestamp == TS
    assert result.market_summary is AIMarketSummary.BULLISH
    assert result.confidence is ReasoningConfidence.HIGH
    assert result.agreement_summary is AgreementSummary.ALIGNED
    assert result.conflict_summary is ConflictSummary.NONE
    assert result.trading_suitability is TradingSuitability.SUITABLE
    assert result.missing_information == ()
    assert result.explanation == (
        "NIFTY 1m context is bullish with high confidence. "
        "Primary agreement is aligned; conflict status is none. "
        "Trading suitability is suitable. "
        "Market phase is trending_up and context strength is strong. "
        "Evidence: price_action=bullish, option_chain=bullish, vwap=bullish, "
        "cpr=bullish, camarilla=neutral. Missing information: none."
    )


def test_conflict_missing_and_insufficient_reasoning():
    conflicted = feed(
        engine(),
        context(
            market_bias=MarketBias.MIXED,
            market_phase=MarketPhase.RANGE,
            agreement=AgreementState.CONFLICTED,
            context_strength=ContextStrength.WEAK,
            price_action_direction=EvidenceDirection.BULLISH,
            option_chain_direction=EvidenceDirection.BEARISH,
            bullish_count=2,
            bearish_count=2,
            neutral_count=0,
            mixed_count=1,
            missing_sources=("cpr",),
            context_evidence=evidence(
                EvidenceDirection.BULLISH,
                EvidenceDirection.BEARISH,
                EvidenceDirection.BULLISH,
                EvidenceDirection.UNKNOWN,
                EvidenceDirection.BEARISH,
            ),
        ),
    )
    assert conflicted.market_summary is AIMarketSummary.MIXED
    assert conflicted.confidence is ReasoningConfidence.LOW
    assert conflicted.agreement_summary is AgreementSummary.CONFLICTED
    assert conflicted.conflict_summary is ConflictSummary.PRIMARY_CONFLICT
    assert conflicted.trading_suitability is TradingSuitability.UNSUITABLE
    assert conflicted.missing_information == ("cpr",)
    assert "Missing information: cpr." in conflicted.explanation
    assert "cpr=" not in conflicted.explanation

    insufficient = feed(
        engine(),
        context(
            market_bias=MarketBias.UNKNOWN,
            market_phase=MarketPhase.UNKNOWN,
            agreement=AgreementState.INSUFFICIENT,
            context_strength=ContextStrength.INSUFFICIENT,
            price_action_direction=EvidenceDirection.UNKNOWN,
            option_chain_direction=EvidenceDirection.UNKNOWN,
            bullish_count=0,
            bearish_count=0,
            neutral_count=0,
            mixed_count=0,
            available_count=0,
            missing_sources=("price_action", "option_chain", "vwap", "cpr", "camarilla"),
            context_evidence=evidence(
                EvidenceDirection.UNKNOWN,
                EvidenceDirection.UNKNOWN,
                EvidenceDirection.UNKNOWN,
                EvidenceDirection.UNKNOWN,
                EvidenceDirection.UNKNOWN,
            ),
        ),
    )
    assert insufficient.market_summary is AIMarketSummary.INSUFFICIENT
    assert insufficient.confidence is ReasoningConfidence.INSUFFICIENT
    assert insufficient.agreement_summary is AgreementSummary.INSUFFICIENT
    assert insufficient.conflict_summary is ConflictSummary.INSUFFICIENT
    assert insufficient.trading_suitability is TradingSuitability.INSUFFICIENT
    assert "Evidence: none." in insufficient.explanation


def test_confidence_suitability_and_secondary_conflict_rules():
    moderate = feed(engine(), context(context_strength=ContextStrength.MODERATE))
    assert moderate.confidence is ReasoningConfidence.MEDIUM
    assert moderate.trading_suitability is TradingSuitability.WATCHLIST

    bearish = feed(engine(), context(market_bias=MarketBias.BEARISH))
    assert bearish.market_summary is AIMarketSummary.BEARISH
    assert bearish.trading_suitability is TradingSuitability.SUITABLE

    neutral = feed(
        engine(),
        context(
            market_bias=MarketBias.NEUTRAL,
            agreement=AgreementState.PARTIAL,
            context_strength=ContextStrength.WEAK,
            bullish_count=0,
            bearish_count=0,
            neutral_count=5,
        ),
    )
    assert neutral.market_summary is AIMarketSummary.NEUTRAL
    assert neutral.confidence is ReasoningConfidence.LOW
    assert neutral.trading_suitability is TradingSuitability.WATCHLIST

    secondary_conflict = feed(
        engine(),
        context(
            agreement=AgreementState.ALIGNED,
            bullish_count=3,
            bearish_count=1,
            context_evidence=evidence(camarilla=EvidenceDirection.BEARISH),
        ),
    )
    assert secondary_conflict.conflict_summary is ConflictSummary.SECONDARY_CONFLICT
    assert secondary_conflict.trading_suitability is TradingSuitability.UNSUITABLE

    mixed = feed(engine(), context(market_bias=MarketBias.MIXED, mixed_count=1, bullish_count=0))
    assert mixed.conflict_summary is ConflictSummary.MIXED_SIGNALS
    assert mixed.trading_suitability is TradingSuitability.WATCHLIST


def test_engine_lifecycle_events_duplicates_corrections_and_reset():
    bus = EventBus()
    events = []
    ai = AIReasoningEngine(bus, "NIFTY", "1m")
    bus.subscribe(AI_DECISION_READY, lambda state: events.append((state, ai.state, ai.data, ai.is_ready())))

    first_context = context()
    first = ai.update(first_context)
    duplicate = ai.update(first_context)
    correction = ai.update(context(market_bias=MarketBias.BEARISH))
    newer = ai.process(context(timestamp=TS + timedelta(minutes=1), market_bias=MarketBias.BEARISH))

    assert first is ai.context or newer is ai.state
    assert duplicate is first
    assert correction is not first
    assert newer is ai.state
    assert ai.data is ai.state
    assert ai.is_ready()
    assert events[0] == (first, first, first, True)
    assert len(events) == 3
    assert_rejected_preserves_state(ai, context(timestamp=TS - timedelta(minutes=1)))

    ai.reset()
    assert ai.context is None and ai.state is None and ai.data is None and not ai.is_ready()
    assert len(events) == 3
    accepted_after_reset = ai.update(context(timestamp=TS - timedelta(minutes=5)))
    assert accepted_after_reset is ai.state
    ai.clear()
    assert ai.context is None and ai.state is None and ai.data is None and not ai.is_ready()


def test_validation_and_independent_instances():
    ai = engine()
    feed(ai)
    assert_rejected_preserves_state(ai, object(), TypeError)
    assert_rejected_preserves_state(ai, context(symbol="BANKNIFTY"))
    assert_rejected_preserves_state(ai, context(timeframe="5m"))
    assert_rejected_preserves_state(ai, context(timestamp="bad"))
    assert_rejected_preserves_state(ai, context(timestamp=TS.replace(tzinfo=timezone.utc)))

    nifty = AIReasoningEngine(EventBus(), "NIFTY", "1m")
    banknifty = AIReasoningEngine(EventBus(), "BANKNIFTY", "1m")
    nifty_state = nifty.update(context())
    banknifty_state = banknifty.update(context(symbol="BANKNIFTY"))
    nifty.reset()
    assert nifty.state is None
    assert banknifty.state == banknifty_state
    assert banknifty.state != nifty_state
