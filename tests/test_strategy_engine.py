"""
Tests for Strategy Engine V1.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from core.event_bus import EventBus
from core.events import STRATEGY_DECISION_READY
from engines.ai_reasoning.enums import (
    AgreementSummary,
    AIMarketSummary,
    ConflictSummary,
    ReasoningConfidence,
    TradingSuitability,
)
from engines.ai_reasoning.models import AIReasoningState
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
from engines.strategy import (
    BlockReason,
    EntryReference,
    SetupQuality,
    StopReference,
    StrategyCalculator,
    StrategyDecision,
    StrategyDecisionState,
    StrategyEngine,
    StrategySnapshot,
    TargetReference,
    TradeDirection,
)


TS = datetime(2026, 7, 10, 10, 0)


SUMMARY_FOR_BIAS = {
    MarketBias.BULLISH: AIMarketSummary.BULLISH,
    MarketBias.BEARISH: AIMarketSummary.BEARISH,
    MarketBias.NEUTRAL: AIMarketSummary.NEUTRAL,
    MarketBias.MIXED: AIMarketSummary.MIXED,
    MarketBias.UNKNOWN: AIMarketSummary.INSUFFICIENT,
}
CONFIDENCE_FOR_STRENGTH = {
    ContextStrength.STRONG: ReasoningConfidence.HIGH,
    ContextStrength.MODERATE: ReasoningConfidence.MEDIUM,
    ContextStrength.WEAK: ReasoningConfidence.LOW,
    ContextStrength.INSUFFICIENT: ReasoningConfidence.INSUFFICIENT,
}
AGREEMENT_FOR_CONTEXT = {
    AgreementState.ALIGNED: AgreementSummary.ALIGNED,
    AgreementState.CONFLICTED: AgreementSummary.CONFLICTED,
    AgreementState.PARTIAL: AgreementSummary.PARTIAL,
    AgreementState.INSUFFICIENT: AgreementSummary.INSUFFICIENT,
}


def assert_raises(expected_error, callback):
    try:
        callback()
    except expected_error:
        return
    raise AssertionError(f"Expected {expected_error}")


def context_evidence():
    return (
        ContextEvidence("price_action", EvidenceDirection.BULLISH, "price_action"),
        ContextEvidence("option_chain", EvidenceDirection.BULLISH, "option_chain"),
    )


def market_context(
    symbol="NIFTY",
    timeframe="1m",
    timestamp=TS,
    market_bias=MarketBias.BULLISH,
    market_phase=MarketPhase.TRENDING_UP,
    agreement=AgreementState.ALIGNED,
    context_strength=ContextStrength.STRONG,
    missing_sources=(),
    camarilla_zone=CamarillaZone.H4_TO_H5,
):
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
        price_action_direction=EvidenceDirection.BULLISH,
        option_chain_direction=EvidenceDirection.BULLISH,
        vwap_position=VWAPPosition.ABOVE,
        cpr_position=CPRPosition.ABOVE,
        virgin_cpr=False,
        camarilla_zone=camarilla_zone,
        bullish_evidence_count=4,
        bearish_evidence_count=0,
        neutral_evidence_count=1,
        mixed_evidence_count=0,
        available_source_count=5,
        evidence=context_evidence(),
        missing_sources=missing_sources,
    )


def ai_reasoning(
    symbol="NIFTY",
    timeframe="1m",
    timestamp=TS,
    market_summary=AIMarketSummary.BULLISH,
    confidence=ReasoningConfidence.HIGH,
    agreement_summary=AgreementSummary.ALIGNED,
    conflict_summary=ConflictSummary.NONE,
    trading_suitability=TradingSuitability.SUITABLE,
    missing_information=(),
):
    return AIReasoningState(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        market_summary=market_summary,
        confidence=confidence,
        agreement_summary=agreement_summary,
        conflict_summary=conflict_summary,
        trading_suitability=trading_suitability,
        missing_information=missing_information,
        explanation="deterministic",
    )


def matching_ai(context, **overrides):
    values = {
        "symbol": context.symbol,
        "timeframe": context.timeframe,
        "timestamp": context.timestamp,
        "market_summary": SUMMARY_FOR_BIAS[context.market_bias],
        "confidence": CONFIDENCE_FOR_STRENGTH[context.context_strength],
        "agreement_summary": AGREEMENT_FOR_CONTEXT[context.agreement],
        "conflict_summary": ConflictSummary.NONE,
        "trading_suitability": TradingSuitability.SUITABLE,
        "missing_information": context.missing_sources,
    }
    values.update(overrides)
    return ai_reasoning(**values)


def snapshot(mc=None, ai=None, symbol="NIFTY", timeframe="1m", timestamp=TS):
    mc = mc or market_context(symbol=symbol, timeframe=timeframe, timestamp=timestamp)
    ai = ai or matching_ai(mc)
    return StrategySnapshot(symbol, timeframe, timestamp, ai, mc)


def engine(symbol=" nifty ", timeframe=" 1m "):
    return StrategyEngine(EventBus(), symbol, timeframe)


def feed(strategy_engine, strategy_snapshot=None):
    return strategy_engine.update(strategy_snapshot or snapshot())


def assert_block(strategy_snapshot, reason):
    state = StrategyCalculator.calculate(strategy_snapshot)
    assert state.decision is StrategyDecision.NO_TRADE
    assert state.direction is TradeDirection.NONE
    assert state.setup_quality is SetupQuality.REJECTED
    assert state.entry_reference is EntryReference.NONE
    assert state.stop_reference is StopReference.NONE
    assert state.target_reference is TargetReference.NONE
    assert state.block_reason is reason
    assert state.rationale[-1] == f"blocked_{reason.value}"
    return state


def assert_rejected_preserves_state(strategy_engine, bad_snapshot, expected_error=ValueError):
    old_snapshot = strategy_engine.snapshot
    old_state = strategy_engine.state
    old_data = strategy_engine.data
    old_ready = strategy_engine.is_ready()
    events = []
    strategy_engine._event_bus.subscribe(STRATEGY_DECISION_READY, events.append)

    assert_raises(expected_error, lambda: strategy_engine.update(bad_snapshot))

    assert strategy_engine.snapshot == old_snapshot
    assert strategy_engine.state == old_state
    assert strategy_engine.data == old_data
    assert strategy_engine.is_ready() == old_ready
    assert events == []


def test_enum_values_models_slots_and_exports():
    assert StrategyDecision.TRADE_ELIGIBLE.value == "trade_eligible"
    assert StrategyDecision.NO_TRADE.value == "no_trade"
    assert TradeDirection.NONE.value == "none"
    assert SetupQuality.LOW.value == "low"
    assert EntryReference.STRUCTURE_BREAK_RETEST.value == "structure_break_retest"
    assert StopReference.BROKEN_STRUCTURE.value == "broken_structure"
    assert TargetReference.OPTION_OI_LEVEL.value == "option_oi_level"
    assert BlockReason.MISSING_PRIMARY_DATA.value == "missing_primary_data"

    snap = snapshot(symbol=" nifty ", timeframe=" 1m ")
    state = StrategyCalculator.calculate(snap)
    assert snap.symbol == "NIFTY"
    assert snap.timeframe == "1m"
    assert not hasattr(snap, "__dict__")
    assert not hasattr(state, "__dict__")
    assert_raises(FrozenInstanceError, lambda: setattr(snap, "symbol", "BANKNIFTY"))
    assert_raises(FrozenInstanceError, lambda: setattr(state, "decision", StrategyDecision.NO_TRADE))
    assert_raises((FrozenInstanceError, TypeError), lambda: setattr(state, "extra", 1))

    from engines.strategy import __all__
    assert __all__ == [
        "StrategyEngine",
        "StrategyCalculator",
        "StrategySnapshot",
        "StrategyDecisionState",
        "StrategyDecision",
        "TradeDirection",
        "SetupQuality",
        "EntryReference",
        "StopReference",
        "TargetReference",
        "BlockReason",
    ]


def test_constructor_normalization_validation_and_initial_lifecycle():
    st = engine()
    assert st.symbol == "NIFTY"
    assert st.timeframe == "1m"
    assert st.snapshot is None
    assert st.state is None
    assert st.data is None
    assert not st.is_ready()
    assert_raises(ValueError, lambda: StrategyEngine(EventBus(), "", "1m"))
    assert_raises(ValueError, lambda: StrategyEngine(EventBus(), 1, "1m"))
    assert_raises(ValueError, lambda: StrategyEngine(EventBus(), "NIFTY", ""))
    assert_raises(ValueError, lambda: StrategyEngine(EventBus(), "NIFTY", 1))


def test_snapshot_validation_and_atomic_rejection():
    st = engine()
    feed(st)
    assert_rejected_preserves_state(st, object(), TypeError)
    assert_rejected_preserves_state(st, snapshot(symbol="BANKNIFTY"))
    assert_rejected_preserves_state(st, snapshot(timeframe="5m"))
    assert_rejected_preserves_state(st, snapshot(timestamp="bad"))
    aware_mc = market_context(timestamp=TS.replace(tzinfo=timezone.utc))
    assert_rejected_preserves_state(st, snapshot(mc=aware_mc, ai=matching_ai(aware_mc), timestamp=aware_mc.timestamp))
    assert_rejected_preserves_state(st, snapshot(ai=object()))
    assert_rejected_preserves_state(st, StrategySnapshot("NIFTY", "1m", TS, matching_ai(market_context()), object()))


def test_cross_state_consistency_validation():
    st = engine()
    feed(st)
    later = TS + timedelta(minutes=1)
    mc = market_context(timestamp=later)
    assert_rejected_preserves_state(st, snapshot(mc=mc, ai=matching_ai(mc, timestamp=later + timedelta(seconds=1)), timestamp=later))
    assert_rejected_preserves_state(st, snapshot(mc=mc, ai=matching_ai(mc, market_summary=AIMarketSummary.BEARISH), timestamp=later))
    assert_rejected_preserves_state(st, snapshot(mc=mc, ai=matching_ai(mc, confidence=ReasoningConfidence.MEDIUM), timestamp=later))
    assert_rejected_preserves_state(st, snapshot(mc=mc, ai=matching_ai(mc, agreement_summary=AgreementSummary.PARTIAL), timestamp=later))
    assert_rejected_preserves_state(st, snapshot(mc=mc, ai=matching_ai(mc, missing_information=("vwap",)), timestamp=later))
    assert_rejected_preserves_state(st, snapshot(mc=market_context(symbol="BANKNIFTY", timestamp=later), ai=matching_ai(mc), timestamp=later))
    assert_rejected_preserves_state(st, snapshot(mc=market_context(timeframe="5m", timestamp=later), ai=matching_ai(mc), timestamp=later))


def test_blocking_rule_priority_and_rejected_references():
    insufficient_mc = market_context(market_bias=MarketBias.UNKNOWN, agreement=AgreementState.INSUFFICIENT, context_strength=ContextStrength.INSUFFICIENT)
    assert_block(snapshot(mc=insufficient_mc, ai=matching_ai(insufficient_mc, trading_suitability=TradingSuitability.INSUFFICIENT)), BlockReason.INSUFFICIENT_CONTEXT)

    missing_mc = market_context(context_strength=ContextStrength.MODERATE, agreement=AgreementState.PARTIAL, missing_sources=("price_action",))
    assert_block(snapshot(mc=missing_mc, ai=matching_ai(missing_mc, trading_suitability=TradingSuitability.WATCHLIST)), BlockReason.MISSING_PRIMARY_DATA)

    conflict_mc = market_context(agreement=AgreementState.CONFLICTED, context_strength=ContextStrength.WEAK)
    assert_block(snapshot(mc=conflict_mc, ai=matching_ai(conflict_mc, conflict_summary=ConflictSummary.PRIMARY_CONFLICT, trading_suitability=TradingSuitability.UNSUITABLE)), BlockReason.PRIMARY_CONFLICT)

    secondary_mc = market_context(context_strength=ContextStrength.MODERATE, agreement=AgreementState.PARTIAL)
    assert_block(snapshot(mc=secondary_mc, ai=matching_ai(secondary_mc, conflict_summary=ConflictSummary.SECONDARY_CONFLICT, trading_suitability=TradingSuitability.WATCHLIST)), BlockReason.SECONDARY_CONFLICT)

    unsuitable = matching_ai(market_context(), trading_suitability=TradingSuitability.UNSUITABLE)
    assert_block(snapshot(ai=unsuitable), BlockReason.UNSUITABLE_CONTEXT)

    low_mc = market_context(context_strength=ContextStrength.WEAK, agreement=AgreementState.PARTIAL)
    assert_block(snapshot(mc=low_mc, ai=matching_ai(low_mc, trading_suitability=TradingSuitability.WATCHLIST)), BlockReason.LOW_CONFIDENCE)

    neutral_mc = market_context(market_bias=MarketBias.NEUTRAL, agreement=AgreementState.PARTIAL, context_strength=ContextStrength.MODERATE)
    assert_block(snapshot(mc=neutral_mc, ai=matching_ai(neutral_mc, trading_suitability=TradingSuitability.WATCHLIST)), BlockReason.NEUTRAL_BIAS)
    mixed_mc = market_context(market_bias=MarketBias.MIXED, agreement=AgreementState.PARTIAL, context_strength=ContextStrength.MODERATE)
    assert_block(snapshot(mc=mixed_mc, ai=matching_ai(mixed_mc, trading_suitability=TradingSuitability.WATCHLIST)), BlockReason.MIXED_BIAS)
    unknown_mc = market_context(market_bias=MarketBias.UNKNOWN, agreement=AgreementState.PARTIAL, context_strength=ContextStrength.MODERATE)
    unknown_ai = ai_reasoning(confidence=ReasoningConfidence.MEDIUM, agreement_summary=AgreementSummary.PARTIAL, trading_suitability=TradingSuitability.WATCHLIST)
    assert_block(snapshot(mc=unknown_mc, ai=unknown_ai), BlockReason.UNKNOWN_BIAS)

    mismatched = snapshot(ai=matching_ai(market_context(), market_summary=AIMarketSummary.BEARISH))
    assert_block(mismatched, BlockReason.DIRECTION_MISMATCH)


def test_bullish_and_bearish_eligibility_quality_references_and_rationale():
    high_bull = StrategyCalculator.calculate(snapshot())
    assert isinstance(high_bull, StrategyDecisionState)
    assert high_bull.decision is StrategyDecision.TRADE_ELIGIBLE
    assert high_bull.direction is TradeDirection.BULLISH
    assert high_bull.setup_quality is SetupQuality.HIGH
    assert high_bull.entry_reference is EntryReference.PRICE_ACTION_RETEST
    assert high_bull.stop_reference is StopReference.LATEST_SWING
    assert high_bull.target_reference is TargetReference.CAMARILLA_LEVEL
    assert high_bull.block_reason is BlockReason.NONE
    assert high_bull.rationale == (
        "bias_bullish",
        "confidence_high",
        "agreement_aligned",
        "phase_trending_up",
        "entry_price_action_retest",
        "target_camarilla_level",
    )

    medium_mc = market_context(market_phase=MarketPhase.TRENDING_DOWN, context_strength=ContextStrength.MODERATE, agreement=AgreementState.PARTIAL, camarilla_zone=CamarillaZone.UNAVAILABLE)
    medium = StrategyCalculator.calculate(snapshot(mc=medium_mc, ai=matching_ai(medium_mc, trading_suitability=TradingSuitability.WATCHLIST)))
    assert medium.decision is StrategyDecision.TRADE_ELIGIBLE
    assert medium.setup_quality is SetupQuality.MEDIUM
    assert medium.entry_reference is EntryReference.PRICE_ACTION_RETEST
    assert medium.stop_reference is StopReference.LATEST_SWING
    assert medium.target_reference is TargetReference.OPTION_OI_LEVEL

    bear_mc = market_context(market_bias=MarketBias.BEARISH, market_phase=MarketPhase.BREAKOUT_DOWN)
    bear = StrategyCalculator.calculate(snapshot(mc=bear_mc, ai=matching_ai(bear_mc)))
    assert bear.decision is StrategyDecision.TRADE_ELIGIBLE
    assert bear.direction is TradeDirection.BEARISH
    assert bear.setup_quality is SetupQuality.HIGH
    assert bear.entry_reference is EntryReference.STRUCTURE_BREAK_RETEST
    assert bear.stop_reference is StopReference.BROKEN_STRUCTURE

    bear_medium_mc = market_context(market_bias=MarketBias.BEARISH, market_phase=MarketPhase.REVERSAL_DOWN, context_strength=ContextStrength.MODERATE, agreement=AgreementState.PARTIAL)
    bear_medium = StrategyCalculator.calculate(snapshot(mc=bear_medium_mc, ai=matching_ai(bear_medium_mc, trading_suitability=TradingSuitability.WATCHLIST)))
    assert bear_medium.direction is TradeDirection.BEARISH
    assert bear_medium.setup_quality is SetupQuality.MEDIUM
    assert bear_medium.entry_reference is EntryReference.STRUCTURE_BREAK_RETEST
    assert bear_medium.stop_reference is StopReference.BROKEN_STRUCTURE


def test_phase_reference_matrix_and_unsuitable_entry_rejection():
    cases = [
        (MarketPhase.BREAKOUT_UP, EntryReference.STRUCTURE_BREAK_RETEST, StopReference.BROKEN_STRUCTURE),
        (MarketPhase.BREAKOUT_DOWN, EntryReference.STRUCTURE_BREAK_RETEST, StopReference.BROKEN_STRUCTURE),
        (MarketPhase.REVERSAL_UP, EntryReference.STRUCTURE_BREAK_RETEST, StopReference.BROKEN_STRUCTURE),
        (MarketPhase.REVERSAL_DOWN, EntryReference.STRUCTURE_BREAK_RETEST, StopReference.BROKEN_STRUCTURE),
        (MarketPhase.TRENDING_UP, EntryReference.PRICE_ACTION_RETEST, StopReference.LATEST_SWING),
        (MarketPhase.TRENDING_DOWN, EntryReference.PRICE_ACTION_RETEST, StopReference.LATEST_SWING),
    ]
    for phase, entry, stop in cases:
        mc = market_context(market_phase=phase)
        result = StrategyCalculator.calculate(snapshot(mc=mc, ai=matching_ai(mc)))
        assert result.entry_reference is entry
        assert result.stop_reference is stop

    for phase in (MarketPhase.RANGE, MarketPhase.UNKNOWN):
        mc = market_context(market_phase=phase)
        result = assert_block(snapshot(mc=mc, ai=matching_ai(mc)), BlockReason.UNSUITABLE_CONTEXT)
        assert result.entry_reference is EntryReference.NONE
        assert result.stop_reference is StopReference.NONE
        assert result.target_reference is TargetReference.NONE


def test_target_reference_priority_and_private_next_structure_fallback():
    cam_mc = market_context(camarilla_zone=CamarillaZone.H5_TO_H6)
    assert StrategyCalculator.calculate(snapshot(mc=cam_mc, ai=matching_ai(cam_mc))).target_reference is TargetReference.CAMARILLA_LEVEL

    oi_mc = market_context(camarilla_zone=CamarillaZone.UNAVAILABLE)
    assert StrategyCalculator.calculate(snapshot(mc=oi_mc, ai=matching_ai(oi_mc))).target_reference is TargetReference.OPTION_OI_LEVEL

    next_mc = market_context(camarilla_zone=CamarillaZone.UNAVAILABLE, missing_sources=("vwap",))
    assert StrategyCalculator._target_reference(snapshot(mc=next_mc, ai=matching_ai(next_mc))) is TargetReference.OPTION_OI_LEVEL

    missing_option_mc = market_context(camarilla_zone=CamarillaZone.UNAVAILABLE, missing_sources=("option_chain",))
    assert StrategyCalculator._target_reference(snapshot(mc=missing_option_mc, ai=matching_ai(missing_option_mc))) is TargetReference.NEXT_STRUCTURE


def test_engine_lifecycle_events_duplicates_corrections_and_independence():
    bus = EventBus()
    events = []
    st = StrategyEngine(bus, "NIFTY", "1m")
    bus.subscribe(STRATEGY_DECISION_READY, lambda state: events.append((state, st.state, st.data, st.is_ready())))

    first_snapshot = snapshot()
    first = st.update(first_snapshot)
    duplicate = st.update(first_snapshot)
    correction_mc = market_context(market_phase=MarketPhase.BREAKOUT_UP)
    correction = st.update(snapshot(mc=correction_mc, ai=matching_ai(correction_mc)))
    newer_mc = market_context(timestamp=TS + timedelta(minutes=1), market_phase=MarketPhase.REVERSAL_UP)
    newer = st.process(snapshot(mc=newer_mc, ai=matching_ai(newer_mc), timestamp=newer_mc.timestamp))

    assert first.decision is StrategyDecision.TRADE_ELIGIBLE
    assert st.snapshot is first_snapshot or st.state is newer
    assert st.data is st.state
    assert st.is_ready()
    assert events[0] == (first, first, first, True)
    assert duplicate is first
    assert correction is not first
    assert newer is st.state
    assert len(events) == 3
    assert_rejected_preserves_state(st, snapshot(timestamp=TS - timedelta(minutes=1)))

    st.reset()
    assert st.snapshot is None and st.state is None and st.data is None and not st.is_ready()
    assert len(events) == 3
    early_mc = market_context(timestamp=TS - timedelta(minutes=5))
    early = st.update(snapshot(mc=early_mc, ai=matching_ai(early_mc), timestamp=early_mc.timestamp))
    assert early is st.state
    st.clear()
    assert st.snapshot is None and st.state is None and st.data is None and not st.is_ready()

    first_engine = StrategyEngine(EventBus(), "NIFTY", "1m")
    second_engine = StrategyEngine(EventBus(), "BANKNIFTY", "1m")
    first_state = first_engine.update(snapshot())
    bank_mc = market_context(symbol="BANKNIFTY")
    second_state = second_engine.update(snapshot(mc=bank_mc, ai=matching_ai(bank_mc), symbol="BANKNIFTY"))
    first_engine.reset()
    assert first_engine.state is None
    assert second_engine.state == second_state
    assert second_engine.state != first_state


def test_no_mutation_of_upstream_objects():
    mc = market_context()
    ai = matching_ai(mc)
    snap = snapshot(mc=mc, ai=ai)
    before = (mc, ai, snap)
    state = StrategyCalculator.calculate(snap)
    assert (mc, ai, snap) == before
    assert state.market_bias is mc.market_bias
    assert state.confidence is ai.confidence
