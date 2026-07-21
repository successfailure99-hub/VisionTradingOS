"""
Tests for AI Confidence Calibration Engine V1.
"""

from dataclasses import FrozenInstanceError, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from application.enums import ExecutionSafetyMode, RuntimeInstrument
from application.models import RuntimeConfiguration
from application.orchestrator import ApplicationOrchestrator
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import (
    AI_CONFIDENCE_BLOCKED,
    AI_CONFIDENCE_CALIBRATED,
    AI_CONFIDENCE_REDUCED,
    AI_CONFIDENCE_STATE_UPDATED,
)
from core.models.candle import Candle
from engines.ai_confidence_calibration import (
    AIConfidenceCalibrationEngine,
    CalibrationDecision,
    ConfidenceBand,
    ConfidenceCalibrationLifecycle,
    ConfidenceCalibrationRequest,
    ConfidenceEvidence,
    EvidenceAlignment,
    EvidenceCategory,
)
from engines.ai_reasoning.enums import (
    AgreementSummary,
    AIMarketSummary,
    ConflictSummary,
    ReasoningConfidence,
    TradingSuitability,
)
from engines.ai_reasoning.models import AIReasoningState
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
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
from engines.option_chain.enums import OptionType, PositioningBias, PressureType
from engines.option_chain.models import OptionChainState, OptionLeg, OptionStrike, StrikeMetric
from engines.price_action.enums import BreakDirection, MarketStructure, Trend
from engines.price_action.models import PriceActionState
from engines.strategy.enums import (
    BlockReason,
    EntryReference,
    SetupQuality,
    StopReference,
    StrategyDecision,
    TargetReference,
    TradeDirection,
)
from engines.strategy.models import StrategyDecisionState
from engines.vwap.levels import VWAPLevels


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
DEFAULT = object()


@dataclass(frozen=True, slots=True)
class SupportingIndicator:
    symbol: str
    timestamp: datetime
    direction: str


def candle(symbol: str = "NIFTY", timestamp: datetime = NOW) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe="1m",
        start_time=timestamp - timedelta(minutes=1),
        end_time=timestamp,
        open=100.0,
        high=102.0,
        low=99.0,
        close=101.0,
        volume=1000,
    )


def ai_state(
    *,
    symbol: str = "NIFTY",
    timestamp: datetime = NOW,
    summary: AIMarketSummary = AIMarketSummary.BULLISH,
) -> AIReasoningState:
    return AIReasoningState(
        symbol=symbol,
        timeframe="1m",
        timestamp=timestamp,
        market_summary=summary,
        confidence=ReasoningConfidence.HIGH,
        agreement_summary=AgreementSummary.ALIGNED,
        conflict_summary=ConflictSummary.NONE,
        trading_suitability=TradingSuitability.SUITABLE,
        missing_information=(),
        explanation="Existing AI reasoning evidence.",
    )


def strategy_state(
    *,
    symbol: str = "NIFTY",
    timestamp: datetime = NOW,
    direction: TradeDirection = TradeDirection.BULLISH,
) -> StrategyDecisionState:
    return StrategyDecisionState(
        symbol=symbol,
        timeframe="1m",
        timestamp=timestamp,
        decision=StrategyDecision.TRADE_ELIGIBLE,
        direction=direction,
        setup_quality=SetupQuality.HIGH,
        entry_reference=EntryReference.PRICE_ACTION_RETEST,
        stop_reference=StopReference.LATEST_SWING,
        target_reference=TargetReference.NEXT_STRUCTURE,
        block_reason=BlockReason.NONE,
        market_bias=MarketBias.BULLISH if direction is TradeDirection.BULLISH else MarketBias.BEARISH,
        market_phase=MarketPhase.TRENDING_UP if direction is TradeDirection.BULLISH else MarketPhase.TRENDING_DOWN,
        confidence=ReasoningConfidence.HIGH,
        trading_suitability=TradingSuitability.SUITABLE,
        rationale=("Existing strategy decision.",),
    )


def price_action(
    *,
    symbol: str = "NIFTY",
    timestamp: datetime = NOW,
    trend: Trend = Trend.BULLISH,
    structure: MarketStructure = MarketStructure.BULLISH,
    bos: BreakDirection = BreakDirection.BULLISH,
) -> PriceActionState:
    return PriceActionState(
        symbol=symbol,
        timeframe="1m",
        candle_count=5,
        last_candle=candle(symbol, timestamp),
        trend=trend,
        latest_swing_high=None,
        latest_swing_low=None,
        previous_swing_high=None,
        previous_swing_low=None,
        latest_break=None,
        market_structure=structure,
        bos_direction=bos,
        updated_at=timestamp,
    )


def option_chain(
    *,
    symbol: str = "NIFTY",
    timestamp: datetime = NOW,
    bias: PositioningBias = PositioningBias.BULLISH,
) -> OptionChainState:
    call = OptionLeg(OptionType.CALL, 10.0, 1000, 100, 50)
    put = OptionLeg(OptionType.PUT, 8.0, 800, 80, 40)
    return OptionChainState(
        symbol=symbol,
        exchange="NFO",
        expiry_date=date(2026, 7, 30),
        timestamp=timestamp,
        underlying_price=100.0,
        atm_strike=100.0,
        strike_count=1,
        total_call_oi=1000,
        total_put_oi=800,
        total_call_change_oi=100,
        total_put_change_oi=80,
        oi_pcr=0.8,
        change_oi_pcr=0.8,
        max_call_oi=StrikeMetric(100.0, 1000),
        max_put_oi=StrikeMetric(100.0, 800),
        max_call_change_oi=StrikeMetric(100.0, 100),
        max_put_change_oi=StrikeMetric(100.0, 80),
        resistance_strike=105.0,
        support_strike=95.0,
        max_pain_strike=100.0,
        call_pressure=PressureType.CALL_UNWINDING,
        put_pressure=PressureType.PUT_WRITING,
        positioning_bias=bias,
        strikes=(OptionStrike(100.0, call, put),),
    )


def market_context(
    *,
    symbol: str = "NIFTY",
    timestamp: datetime = NOW,
    bias: MarketBias = MarketBias.BULLISH,
    phase: MarketPhase = MarketPhase.TRENDING_UP,
    price: float = 100.0,
    vwap_position: VWAPPosition = VWAPPosition.ABOVE,
) -> MarketContextState:
    return MarketContextState(
        symbol=symbol,
        timeframe="1m",
        timestamp=timestamp,
        current_price=price,
        session_high=105.0,
        session_low=95.0,
        market_bias=bias,
        market_phase=phase,
        agreement=AgreementState.ALIGNED,
        context_strength=ContextStrength.STRONG,
        price_action_direction=EvidenceDirection.BULLISH,
        option_chain_direction=EvidenceDirection.BULLISH,
        vwap_position=vwap_position,
        cpr_position=CPRPosition.ABOVE,
        virgin_cpr=False,
        camarilla_zone=CamarillaZone.H3_TO_H4,
        bullish_evidence_count=4,
        bearish_evidence_count=0,
        neutral_evidence_count=0,
        mixed_evidence_count=0,
        available_source_count=4,
        evidence=(ContextEvidence("price_action", EvidenceDirection.BULLISH, "detail"),),
        missing_sources=(),
    )


def cpr_levels(trading_date: date = NOW.date()) -> CPRLevels:
    return CPRLevels(
        trading_date=trading_date,
        previous_high=105.0,
        previous_low=95.0,
        previous_close=100.0,
        pivot=100.0,
        bc=96.0,
        tc=97.0,
        width=1.0,
        width_percentage=1.0,
    )


def camarilla_levels(trading_date: date = NOW.date()) -> CamarillaLevels:
    return CamarillaLevels(
        trading_date=trading_date,
        previous_high=105.0,
        previous_low=95.0,
        previous_close=100.0,
        pivot=100.0,
        h3=98.0,
        h4=101.0,
        h5=104.0,
        h6=107.0,
        l3=96.0,
        l4=93.0,
        l5=90.0,
        l6=87.0,
    )


def vwap_levels(*, symbol: str = "NIFTY", timestamp: datetime = NOW, value: float = 95.0) -> VWAPLevels:
    return VWAPLevels(
        symbol=Instrument.from_symbol(symbol),
        trading_date=timestamp.date(),
        timestamp=timestamp,
        vwap=value,
        cumulative_volume=1000,
        cumulative_price_volume=value * 1000,
    )


def request(
    *,
    calibration_id: str = "cal-1",
    timestamp: datetime = NOW,
    instrument: str | RuntimeInstrument = RuntimeInstrument.NIFTY,
    ai_summary: AIMarketSummary = AIMarketSummary.BULLISH,
    direction: TradeDirection = TradeDirection.BULLISH,
    pa=DEFAULT,
    oc=DEFAULT,
    mc=DEFAULT,
    cpr=DEFAULT,
    camarilla=DEFAULT,
    vwap=DEFAULT,
    indicators=DEFAULT,
) -> ConfidenceCalibrationRequest:
    symbol = instrument.value if isinstance(instrument, RuntimeInstrument) else str(instrument).strip().upper()
    return ConfidenceCalibrationRequest(
        calibration_id=calibration_id,
        timestamp=timestamp,
        instrument=instrument,
        ai_reasoning=ai_state(symbol=symbol, timestamp=timestamp, summary=ai_summary),
        strategy_decision=strategy_state(symbol=symbol, timestamp=timestamp, direction=direction),
        price_action=price_action(symbol=symbol, timestamp=timestamp) if pa is DEFAULT else pa,
        option_chain=option_chain(symbol=symbol, timestamp=timestamp) if oc is DEFAULT else oc,
        market_context=market_context(symbol=symbol, timestamp=timestamp) if mc is DEFAULT else mc,
        cpr=cpr_levels(timestamp.date()) if cpr is DEFAULT else cpr,
        camarilla=camarilla_levels(timestamp.date()) if camarilla is DEFAULT else camarilla,
        vwap=vwap_levels(symbol=symbol, timestamp=timestamp) if vwap is DEFAULT else vwap,
        supporting_indicators=(SupportingIndicator(symbol, timestamp, "bullish"),) if indicators is DEFAULT else indicators,
    )


def started_engine(symbol: str = "NIFTY") -> AIConfidenceCalibrationEngine:
    engine = AIConfidenceCalibrationEngine(EventBus(), symbol, "1m")
    engine.start()
    return engine


def evidence(result, category: EvidenceCategory):
    return next(item for item in result.evidence if item.category is category)


def test_all_supporting_evidence_scores_very_high_and_trusts_without_changing_direction():
    result = started_engine().calibrate(request())

    assert result.direction is TradeDirection.BULLISH
    assert result.raw_score == 100.0
    assert result.penalty_score == 0.0
    assert result.final_score == 100.0
    assert result.confidence_band is ConfidenceBand.VERY_HIGH
    assert result.calibration_decision is CalibrationDecision.TRUST
    assert result.supporting_categories == (
        EvidenceCategory.PRICE_ACTION,
        EvidenceCategory.OPTION_CHAIN,
        EvidenceCategory.MARKET_CONTEXT,
        EvidenceCategory.CPR_CAMARILLA,
        EvidenceCategory.VWAP,
        EvidenceCategory.SUPPORTING_INDICATORS,
    )


def test_conflicting_evidence_reduces_score_without_primary_direction_conflict():
    result = started_engine().calibrate(
        request(
            calibration_id="conflicts",
            pa=price_action(trend=Trend.BEARISH, structure=MarketStructure.BEARISH, bos=BreakDirection.BEARISH),
            oc=option_chain(bias=PositioningBias.BEARISH),
            mc=market_context(bias=MarketBias.BEARISH, phase=MarketPhase.TRENDING_DOWN, price=90.0, vwap_position=VWAPPosition.BELOW),
            vwap=vwap_levels(value=95.0),
            indicators=(SupportingIndicator("NIFTY", NOW, "bearish"),),
        )
    )

    assert result.raw_score == 0.0
    assert result.final_score == 0.0
    assert result.confidence_band is ConfidenceBand.VERY_LOW
    assert result.calibration_decision is CalibrationDecision.REDUCE
    assert result.conflicting_categories == (
        EvidenceCategory.PRICE_ACTION,
        EvidenceCategory.OPTION_CHAIN,
        EvidenceCategory.MARKET_CONTEXT,
        EvidenceCategory.CPR_CAMARILLA,
        EvidenceCategory.VWAP,
        EvidenceCategory.SUPPORTING_INDICATORS,
    )


def test_primary_price_action_option_chain_conflict_blocks_decision():
    result = started_engine().calibrate(
        request(
            calibration_id="primary-conflict",
            pa=price_action(),
            oc=option_chain(bias=PositioningBias.BEARISH),
        )
    )

    assert result.confidence_band is ConfidenceBand.BLOCKED
    assert result.calibration_decision is CalibrationDecision.BLOCK
    assert "primary_evidence_conflict" in result.blocked_reasons


def test_missing_both_primary_sources_blocks_decision():
    result = started_engine().calibrate(request(calibration_id="missing-primary", pa=None, oc=None))

    assert result.calibration_decision is CalibrationDecision.BLOCK
    assert "primary_evidence_missing" in result.blocked_reasons
    assert EvidenceCategory.PRICE_ACTION in result.missing_categories
    assert EvidenceCategory.OPTION_CHAIN in result.missing_categories


def test_one_missing_primary_source_applies_required_penalty():
    result = started_engine().calibrate(request(calibration_id="one-missing", pa=None))

    assert result.penalty_score == 20.0
    assert result.final_score == 80.0
    assert result.calibration_decision is CalibrationDecision.TRUST


def test_invalid_primary_source_blocks_without_crashing():
    result = started_engine().calibrate(request(calibration_id="invalid-primary", pa=object()))

    assert result.calibration_decision is CalibrationDecision.BLOCK
    assert "price_action_invalid" in result.blocked_reasons
    assert EvidenceCategory.PRICE_ACTION in result.invalid_categories


def test_both_primary_sources_stale_block_decision():
    stale = NOW - timedelta(seconds=301)
    result = started_engine().calibrate(
        request(
            calibration_id="stale-primary",
            pa=price_action(timestamp=stale),
            oc=option_chain(timestamp=NOW - timedelta(seconds=181)),
        )
    )

    assert result.calibration_decision is CalibrationDecision.BLOCK
    assert "primary_evidence_stale" in result.blocked_reasons
    assert EvidenceCategory.PRICE_ACTION in result.stale_categories
    assert EvidenceCategory.OPTION_CHAIN in result.stale_categories


def test_ai_strategy_direction_mismatch_blocks_without_changing_strategy_direction():
    result = started_engine().calibrate(request(calibration_id="ai-mismatch", ai_summary=AIMarketSummary.BEARISH))

    assert result.direction is TradeDirection.BULLISH
    assert result.calibration_decision is CalibrationDecision.BLOCK
    assert "ai_strategy_direction_mismatch" in result.blocked_reasons


@pytest.mark.parametrize(
    ("score_case", "expected_band", "expected_decision"),
    (
        ("very_low", ConfidenceBand.VERY_LOW, CalibrationDecision.REDUCE),
        ("low", ConfidenceBand.LOW, CalibrationDecision.REDUCE),
        ("moderate", ConfidenceBand.MODERATE, CalibrationDecision.TRUST),
        ("high", ConfidenceBand.HIGH, CalibrationDecision.TRUST),
        ("very_high", ConfidenceBand.VERY_HIGH, CalibrationDecision.TRUST),
    ),
)
def test_confidence_bands_and_reduce_threshold(score_case, expected_band, expected_decision):
    neutral_pa = price_action(trend=Trend.RANGE, structure=MarketStructure.RANGE, bos=BreakDirection.NONE)
    neutral_oc = option_chain(bias=PositioningBias.NEUTRAL)
    neutral_mc = market_context(bias=MarketBias.NEUTRAL, phase=MarketPhase.RANGE, price=100.0, vwap_position=VWAPPosition.AT)
    values = {
        "very_low": dict(pa=neutral_pa, oc=neutral_oc, mc=market_context(bias=MarketBias.BEARISH, phase=MarketPhase.TRENDING_DOWN, price=90.0, vwap_position=VWAPPosition.BELOW), vwap=vwap_levels(value=95.0), indicators=(SupportingIndicator("NIFTY", NOW, "bearish"),), cpr=None, camarilla=None),
        "low": dict(pa=neutral_pa, oc=neutral_oc, mc=market_context(bias=MarketBias.BEARISH, phase=MarketPhase.TRENDING_DOWN), indicators=(SupportingIndicator("NIFTY", NOW, "bearish"),), cpr=None, camarilla=None, vwap=None),
        "moderate": dict(pa=neutral_pa, oc=neutral_oc, mc=neutral_mc, cpr=None, camarilla=None, vwap=None, indicators=()),
        "high": dict(pa=price_action(), oc=neutral_oc, mc=neutral_mc, cpr=None, camarilla=None, vwap=None, indicators=()),
        "very_high": {},
    }
    result = started_engine().calibrate(request(calibration_id=score_case, **values[score_case]))

    assert result.confidence_band is expected_band
    assert result.calibration_decision is expected_decision


def test_each_evidence_category_has_deterministic_weights():
    result = started_engine().calibrate(request())
    contributions = {item.category: item.contribution for item in result.evidence}

    assert contributions == {
        EvidenceCategory.PRICE_ACTION: 30.0,
        EvidenceCategory.OPTION_CHAIN: 30.0,
        EvidenceCategory.MARKET_CONTEXT: 15.0,
        EvidenceCategory.CPR_CAMARILLA: 10.0,
        EvidenceCategory.VWAP: 8.0,
        EvidenceCategory.SUPPORTING_INDICATORS: 7.0,
    }


def test_secondary_evidence_staleness_is_reported_without_primary_block():
    result = started_engine().calibrate(
        request(
            calibration_id="stale-secondary",
            mc=market_context(timestamp=NOW - timedelta(seconds=901)),
            vwap=vwap_levels(timestamp=NOW - timedelta(seconds=301)),
            indicators=(SupportingIndicator("NIFTY", NOW - timedelta(seconds=301), "bullish"),),
        )
    )

    assert result.calibration_decision is CalibrationDecision.TRUST
    assert EvidenceCategory.MARKET_CONTEXT in result.stale_categories
    assert EvidenceCategory.VWAP in result.stale_categories
    assert EvidenceCategory.SUPPORTING_INDICATORS in result.stale_categories


def test_daily_cpr_camarilla_future_dates_are_rejected():
    with pytest.raises(ValueError, match="cpr trading date cannot be in the future"):
        request(cpr=cpr_levels(NOW.date() + timedelta(days=1)))

    with pytest.raises(ValueError, match="camarilla trading date cannot be in the future"):
        request(camarilla=camarilla_levels(NOW.date() + timedelta(days=1)))


def test_future_intraday_evidence_timestamp_is_rejected():
    with pytest.raises(ValueError, match="price_action timestamp cannot be in the future"):
        request(pa=price_action(timestamp=NOW + timedelta(seconds=1)))


def test_naive_request_clock_is_rejected():
    with pytest.raises(ValueError, match="timestamp must be timezone-aware datetime"):
        request(timestamp=datetime(2026, 7, 21, 10, 0))


def test_supported_instruments_are_nifty_banknifty_and_sensex_only():
    for instrument in (RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.SENSEX):
        req = request(
            calibration_id=instrument.value,
            instrument=instrument,
            ai_summary=AIMarketSummary.NEUTRAL,
            direction=TradeDirection.NONE,
            pa=price_action(symbol=instrument.value, trend=Trend.RANGE, structure=MarketStructure.RANGE, bos=BreakDirection.NONE),
            oc=option_chain(symbol=instrument.value, bias=PositioningBias.NEUTRAL),
            mc=market_context(symbol=instrument.value, bias=MarketBias.NEUTRAL, phase=MarketPhase.RANGE),
            vwap=vwap_levels(symbol=instrument.value),
            indicators=(SupportingIndicator(instrument.value, NOW, "neutral"),),
        )
        assert req.instrument is instrument

    with pytest.raises(ValueError, match="unsupported instrument"):
        request(instrument="FINNIFTY")


def test_cross_instrument_request_is_rejected_before_scoring():
    with pytest.raises(ValueError, match="ai_reasoning instrument does not match request"):
        ConfidenceCalibrationRequest(
            calibration_id="cross",
            timestamp=NOW,
            instrument=RuntimeInstrument.NIFTY,
            ai_reasoning=ai_state(symbol="BANKNIFTY"),
            strategy_decision=strategy_state(),
        )


def test_duplicate_calibration_id_is_idempotent_for_same_request_and_rejects_mutation():
    engine = started_engine()
    req = request(calibration_id="dupe")

    first = engine.calibrate(req)
    second = engine.calibrate(req)

    assert second is first
    assert engine.snapshot().calibration_count == 1
    with pytest.raises(ValueError, match="calibration_id already exists"):
        engine.calibrate(request(calibration_id="dupe", oc=option_chain(bias=PositioningBias.NEUTRAL)))


def test_events_publish_state_calibrated_reduced_and_blocked():
    bus = EventBus()
    seen = []
    for event in (AI_CONFIDENCE_STATE_UPDATED, AI_CONFIDENCE_CALIBRATED, AI_CONFIDENCE_REDUCED, AI_CONFIDENCE_BLOCKED):
        bus.subscribe(event, lambda payload, event=event: seen.append((event, payload)))
    engine = AIConfidenceCalibrationEngine(bus, "NIFTY", "1m")

    engine.start()
    engine.calibrate(request(calibration_id="reduced", pa=price_action(trend=Trend.RANGE, structure=MarketStructure.RANGE, bos=BreakDirection.NONE), oc=option_chain(bias=PositioningBias.NEUTRAL), mc=market_context(bias=MarketBias.BEARISH, phase=MarketPhase.TRENDING_DOWN), indicators=(SupportingIndicator("NIFTY", NOW, "bearish"),), cpr=None, camarilla=None, vwap=None))
    engine.calibrate(request(calibration_id="blocked", oc=option_chain(bias=PositioningBias.BEARISH)))

    event_names = [name for name, _ in seen]
    assert AI_CONFIDENCE_STATE_UPDATED in event_names
    assert AI_CONFIDENCE_CALIBRATED in event_names
    assert AI_CONFIDENCE_REDUCED in event_names
    assert AI_CONFIDENCE_BLOCKED in event_names


def test_lifecycle_requires_start_and_stops_deterministically():
    engine = AIConfidenceCalibrationEngine(EventBus(), "NIFTY", "1m")

    with pytest.raises(RuntimeError, match="must be started"):
        engine.calibrate(request())
    assert engine.start().lifecycle_state is ConfidenceCalibrationLifecycle.READY
    assert engine.stop().lifecycle_state is ConfidenceCalibrationLifecycle.STOPPED
    with pytest.raises(RuntimeError, match="stopped"):
        engine.calibrate(request())
    assert engine.reset().lifecycle_state is ConfidenceCalibrationLifecycle.READY


def test_models_are_immutable():
    result = started_engine().calibrate(request())
    with pytest.raises(FrozenInstanceError):
        result.final_score = 1.0
    with pytest.raises(FrozenInstanceError):
        result.evidence[0].contribution = 1.0


def test_result_and_evidence_reject_non_finite_scores():
    with pytest.raises(ValueError, match="final_score must be finite"):
        result = started_engine().calibrate(request())
        type(result)(
            calibration_id=result.calibration_id,
            timestamp=result.timestamp,
            instrument=result.instrument,
            direction=result.direction,
            raw_score=result.raw_score,
            penalty_score=result.penalty_score,
            final_score=float("nan"),
            confidence_band=result.confidence_band,
            calibration_decision=result.calibration_decision,
            primary_reason=result.primary_reason,
            evidence=result.evidence,
            supporting_categories=result.supporting_categories,
            conflicting_categories=result.conflicting_categories,
            missing_categories=result.missing_categories,
            stale_categories=result.stale_categories,
            invalid_categories=result.invalid_categories,
            blocked_reasons=result.blocked_reasons,
        )
    with pytest.raises(ValueError, match="contribution must be finite"):
        ConfidenceEvidence(
            category=EvidenceCategory.PRICE_ACTION,
            alignment=EvidenceAlignment.SUPPORTS,
            maximum_weight=30,
            contribution=float("inf"),
            reason_code="reason",
            explanation="explanation",
            source_timestamp=NOW,
            age_seconds=0.0,
        )


def test_runtime_snapshot_contains_confidence_snapshot_and_reset_only_clears_calibration_state():
    app = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.NIFTY,),
            safety_mode=ExecutionSafetyMode.ANALYSIS_ONLY,
        ),
    )
    app.start()
    app.calibrate_ai_confidence(RuntimeInstrument.NIFTY, request())

    snapshot = app.snapshot().runtime_snapshots[0].confidence_calibration
    assert snapshot is not None
    assert snapshot.calibration_count == 1
    assert snapshot.broker_order_calls == 0
    assert snapshot.mutation_calls == 0
    assert snapshot.live_order_submission_enabled is False

    app.reset_confidence_calibration(RuntimeInstrument.NIFTY)
    after_reset = app.get_confidence_snapshot(RuntimeInstrument.NIFTY)
    assert after_reset.calibration_count == 0
    assert after_reset.lifecycle_state is ConfidenceCalibrationLifecycle.READY
    app.stop()


def test_runtime_rejects_wrong_instrument_calibration_request():
    app = ApplicationOrchestrator(EventBus(), RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY)))
    app.start()

    with pytest.raises(ValueError, match="does not match SymbolRuntime"):
        app.calibrate_ai_confidence(RuntimeInstrument.BANKNIFTY, request(instrument=RuntimeInstrument.NIFTY))
    app.stop()


def test_engine_package_contains_no_execution_network_threading_or_runtime_creation_calls():
    package = Path("engines/ai_confidence_calibration")
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))

    for forbidden in (
        "place_order",
        "modify_order",
        "cancel_order",
        "execute_paper_plan",
        "reconcile_paper_execution",
        "apply_position",
        "run_strategy",
        "run_risk",
        "openai",
        "requests",
        "httpx",
        "threading",
        "asyncio",
        "time.sleep",
        "QTimer",
        "EventBus(",
    ):
        assert forbidden not in source


def test_snapshot_permanent_read_only_safety_constants_remain_zero_and_false():
    snapshot = started_engine().snapshot()

    assert snapshot.broker_order_calls == 0
    assert snapshot.mutation_calls == 0
    assert snapshot.live_order_submission_enabled is False
