from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta

import pytest

from application import ApplicationBootstrap, ExecutionSafetyMode, RuntimeConfiguration, RuntimeInstrument
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.models.candle import Candle
from core.models.tick import Tick
from dashboard.presenters import build_strategy_view
from engines.ai_reasoning.enums import AIMarketSummary, AgreementSummary, ConflictSummary, ReasoningConfidence, TradingSuitability
from engines.ai_reasoning.models import AIReasoningState
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context.enums import AgreementState, CPRPosition, CamarillaZone, ContextStrength, EvidenceDirection, MarketBias, MarketPhase, VWAPPosition
from engines.market_context.models import MarketContextState
from engines.option_chain.enums import OptionType, PositioningBias, PressureType
from engines.option_chain.models import OptionChainState, OptionLeg, OptionStrike, StrikeMetric
from engines.price_action.enums import BreakDirection, LiquiditySweep, MarketStructure, PullbackState, RangeState, StructureType, SwingType, Trend
from engines.price_action.models import PriceActionState, SwingPoint
from engines.risk import InstrumentLotSize, RiskConfiguration, RiskDecision, RiskTradePlanEngine, TradePlan
from engines.strategy.enums import BlockReason, EntryReference, SetupQuality, StopReference, StrategyDecision, TargetReference, TradeDirection
from engines.strategy.models import StrategyDecisionState


NOW = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)


def config(**overrides):
    values = dict(
        capital=100000.0,
        risk_per_trade_percentage=1.0,
        maximum_risk_per_trade_amount=1000.0,
        maximum_lots=2,
        minimum_reward_risk=1.5,
        maximum_stop_distance_percentage=10.0,
        maximum_trades_per_day=3,
        maximum_daily_loss=5000.0,
        lot_sizes=(InstrumentLotSize("NIFTY", 75), InstrumentLotSize("BANKNIFTY", 15), InstrumentLotSize("SENSEX", 20)),
    )
    values.update(overrides)
    return RiskConfiguration(**values)


def strategy(symbol="NIFTY", direction=TradeDirection.BULLISH, confidence=ReasoningConfidence.HIGH, decision=StrategyDecision.TRADE_ELIGIBLE, block=BlockReason.NONE, ts=NOW):
    return StrategyDecisionState(
        symbol=symbol,
        timeframe="1m",
        timestamp=ts,
        decision=decision,
        direction=direction,
        setup_quality=SetupQuality.HIGH,
        entry_reference=EntryReference.STRUCTURE_BREAK_RETEST,
        stop_reference=StopReference.BROKEN_STRUCTURE,
        target_reference=TargetReference.CAMARILLA_LEVEL,
        block_reason=block,
        market_bias=MarketBias.BEARISH if direction is TradeDirection.BEARISH else MarketBias.BULLISH,
        market_phase=MarketPhase.TRENDING_DOWN if direction is TradeDirection.BEARISH else MarketPhase.TRENDING_UP,
        confidence=confidence,
        trading_suitability=TradingSuitability.SUITABLE,
        rationale=("eligible",),
    )


def context(symbol="NIFTY", direction=TradeDirection.BULLISH, price=100.0, agreement=AgreementState.ALIGNED, ts=NOW):
    bearish = direction is TradeDirection.BEARISH
    return MarketContextState(
        symbol=symbol,
        timeframe="1m",
        timestamp=ts,
        current_price=price,
        session_high=108.0,
        session_low=92.0,
        market_bias=MarketBias.BEARISH if bearish else MarketBias.BULLISH,
        market_phase=MarketPhase.TRENDING_DOWN if bearish else MarketPhase.TRENDING_UP,
        agreement=agreement,
        context_strength=ContextStrength.STRONG,
        price_action_direction=EvidenceDirection.BEARISH if bearish else EvidenceDirection.BULLISH,
        option_chain_direction=EvidenceDirection.BEARISH if bearish else EvidenceDirection.BULLISH,
        vwap_position=VWAPPosition.BELOW if bearish else VWAPPosition.ABOVE,
        cpr_position=CPRPosition.BELOW if bearish else CPRPosition.ABOVE,
        virgin_cpr=False,
        camarilla_zone=CamarillaZone.L5_TO_L4 if bearish else CamarillaZone.H3_TO_H4,
        bullish_evidence_count=0 if bearish else 5,
        bearish_evidence_count=5 if bearish else 0,
        neutral_evidence_count=0,
        mixed_evidence_count=0,
        available_source_count=5,
        evidence=(),
        missing_sources=(),
    )


def ai(symbol="NIFTY", direction=TradeDirection.BULLISH, confidence=ReasoningConfidence.HIGH, ts=NOW):
    bearish = direction is TradeDirection.BEARISH
    return AIReasoningState(
        symbol=symbol,
        timeframe="1m",
        timestamp=ts,
        market_summary=AIMarketSummary.BEARISH if bearish else AIMarketSummary.BULLISH,
        confidence=confidence,
        agreement_summary=AgreementSummary.ALIGNED,
        conflict_summary=ConflictSummary.NONE,
        trading_suitability=TradingSuitability.SUITABLE,
        missing_information=(),
        explanation="risk test",
    )


def swing(price, kind=SwingType.LOW, structure=StructureType.HIGHER_LOW):
    return SwingPoint("NIFTY", "1m", kind, structure, price, NOW, NOW, 1)


def price_action(direction=TradeDirection.BULLISH):
    candle = Candle("NIFTY", "1m", NOW, NOW, 100.0, 101.0, 99.0, 100.0, 10)
    if direction is TradeDirection.BEARISH:
        return PriceActionState(
            "NIFTY", "1m", 10, candle, Trend.BEARISH,
            swing(103.0, SwingType.HIGH, StructureType.LOWER_HIGH), swing(92.0),
            None, None, None, MarketStructure.BEARISH, latest_lh=swing(103.0, SwingType.HIGH, StructureType.LOWER_HIGH),
            swing_high=swing(103.0, SwingType.HIGH, StructureType.LOWER_HIGH), current_structure_high=103.0, current_structure_low=92.0,
            bos_direction=BreakDirection.BEARISH, pullback_state=PullbackState.BEARISH_PULLBACK, range_state=RangeState.NOT_RANGE, liquidity_sweep=LiquiditySweep.NONE, updated_at=NOW,
        )
    return PriceActionState(
        "NIFTY", "1m", 10, candle, Trend.BULLISH,
        swing(108.0, SwingType.HIGH, StructureType.HIGHER_HIGH), swing(96.0),
        None, None, None, MarketStructure.BULLISH, latest_hl=swing(96.0), swing_low=swing(96.0),
        current_structure_high=108.0, current_structure_low=96.0,
        bos_direction=BreakDirection.BULLISH, pullback_state=PullbackState.BULLISH_PULLBACK, range_state=RangeState.NOT_RANGE, liquidity_sweep=LiquiditySweep.NONE, updated_at=NOW,
    )


def option_chain(symbol="NIFTY"):
    strikes = (OptionStrike(100.0, OptionLeg(OptionType.CALL, 10.0, 100, 10, 10), OptionLeg(OptionType.PUT, 8.0, 90, 5, 10)),)
    return OptionChainState(symbol, "NSE", date(2026, 7, 30), NOW, 100.0, 100.0, 1, 100, 90, 10, 5, 0.9, 0.5, StrikeMetric(100.0, 100), StrikeMetric(100.0, 90), StrikeMetric(100.0, 10), StrikeMetric(100.0, 5), 101.0, 99.0, 100.0, PressureType.BALANCED, PressureType.BALANCED, PositioningBias.NEUTRAL, strikes)


def cam():
    return CamarillaLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 106.0, 110.0, 112.0, 118.0, 94.0, 90.0, 88.0, 82.0)


def cpr():
    return CPRLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 99.0, 101.0, 2.0, 2.0)


def evaluate(**overrides):
    direction = overrides.pop("direction", TradeDirection.BULLISH)
    item = RiskTradePlanEngine()
    return item, item.evaluate(
        symbol=overrides.pop("symbol", "NIFTY"),
        timeframe="1m",
        strategy=overrides.pop("strategy", strategy(direction=direction)),
        configuration=overrides.pop("configuration", config()),
        market_context=overrides.pop("market_context", context(direction=direction)),
        price_action=overrides.pop("price_action_state", price_action(direction)),
        option_chain=overrides.pop("option_chain_state", option_chain()),
        camarilla=overrides.pop("camarilla", cam()),
        cpr=overrides.pop("cpr", cpr()),
        latest_tick=overrides.pop("latest_tick", Tick(Instrument.NIFTY, Exchange.NSE, NOW, 100.0, 1, 99.5, 100.5, 0)),
        position=overrides.pop("position", None),
        now=overrides.pop("now", NOW),
    )


def test_risk_configuration_and_trade_plan_models_are_validated_and_immutable():
    with pytest.raises(ValueError):
        RiskConfiguration(capital=0)
    with pytest.raises(ValueError):
        RiskConfiguration(risk_per_trade_percentage=-1)
    with pytest.raises(ValueError):
        InstrumentLotSize("NIFTY", 0)
    item, state = evaluate()
    plan = item.active_plan
    assert plan.approved_quantity == plan.approved_lots * plan.lot_size
    with pytest.raises(FrozenInstanceError):
        plan.status = "OPEN"


@pytest.mark.parametrize("direction", (TradeDirection.BULLISH, TradeDirection.BEARISH))
def test_valid_directional_setups_are_approved_and_never_reversed(direction):
    item, state = evaluate(direction=direction)
    assert state.decision is RiskDecision.APPROVED
    assert state.direction is direction
    assert state.approved_lots <= 2
    assert state.approved_quantity == state.approved_lots * state.lot_size
    assert state.estimated_risk_amount <= state.risk_budget
    assert state.reward_risk_ratio >= 1.5
    assert item.active_plan.status == "READY"


def test_position_sizing_uses_lot_size_and_never_rounds_up():
    _, state = evaluate(configuration=config(capital=50000.0, risk_per_trade_percentage=1.0, maximum_lots=10))
    assert state.risk_budget == 500.0
    assert state.lot_size == 75
    assert state.approved_lots == 1
    assert state.approved_quantity == 75
    assert state.estimated_risk_amount == 300.0


def test_rejections_cover_low_confidence_missing_sources_poor_reward_and_missing_capital():
    _, low = evaluate(strategy=strategy(confidence=ReasoningConfidence.LOW))
    assert low.decision is RiskDecision.REJECTED
    assert low.risk_reason == "AI confidence below risk threshold"
    _, missing = evaluate(price_action_state=None)
    assert missing.risk_reason == "Price Action evidence is required"
    poor_cam = CamarillaLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 101.0, 101.5, 112.0, 118.0, 98.0, 94.0, 88.0, 82.0)
    _, poor = evaluate(camarilla=poor_cam)
    assert poor.risk_reason == "Reward/risk below minimum 1.50"
    _, no_capital = evaluate(configuration=config(capital=None))
    assert no_capital.risk_reason == "Trading capital not configured"


def test_duplicate_plan_returns_existing_state_without_reserving_twice_and_expiry_replaces():
    item, first = evaluate()
    daily = item.daily_state
    second = item.evaluate(symbol="NIFTY", timeframe="1m", strategy=strategy(), configuration=config(), market_context=context(), price_action=price_action(), option_chain=option_chain(), camarilla=cam(), cpr=cpr(), now=NOW + timedelta(minutes=1))
    assert second is first
    assert item.daily_state == daily
    later_strategy = strategy(ts=NOW + timedelta(minutes=20))
    later = item.evaluate(symbol="NIFTY", timeframe="1m", strategy=later_strategy, configuration=config(), market_context=context(ts=NOW + timedelta(minutes=20)), price_action=price_action(), option_chain=option_chain(), camarilla=cam(), cpr=cpr(), now=NOW + timedelta(minutes=20))
    assert later.plan_id != first.plan_id
    assert item.daily_state.plans_approved == 2


def test_runtime_integration_updates_dashboard_without_order_position_or_journal_side_effects():
    cfg = RuntimeConfiguration(
        instruments=(RuntimeInstrument.NIFTY,),
        risk_configuration=config(maximum_lots=1),
    )
    manager = ApplicationBootstrap(cfg).create_application()
    manager.start()
    runtime = manager.orchestrator.get_runtime("NIFTY")
    runtime._last_tick = Tick(Instrument.NIFTY, Exchange.NSE, NOW, 100.0, 1, 99.5, 100.5, 0)
    runtime.price_action_engine._data = price_action()
    runtime.option_chain_engine._state = option_chain()
    runtime.camarilla_engine._levels = cam()
    runtime.cpr_engine._levels = cpr()
    runtime.ai_reasoning_engine._state = ai()
    runtime.market_context_engine._state = context()
    runtime.run_strategy(context(), ai())
    snapshot = runtime.snapshot()
    assert snapshot.risk.decision is RiskDecision.APPROVED
    view = build_strategy_view(snapshot)
    assert view.risk_decision == "Approved"
    assert view.latest_order_status == "Trade Plan Ready"
    assert view.approved_quantity == 75
    assert snapshot.latest_order is None
    assert snapshot.position is None
    assert snapshot.latest_journal_record is None
    assert manager.snapshot().orchestrator_snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert manager.snapshot().orchestrator_snapshot.broker_mode is BrokerExecutionMode.DRY_RUN
