from dataclasses import replace
from datetime import date

from application.bootstrap import ApplicationBootstrap
from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.ai_reasoning_v2 import AIReasoningV2Engine
from engines.ai_reasoning_v2.enums import AIReasoningDirection, AIReasoningState
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context_v2 import MarketContextV2Engine
from engines.market_context_v2.enums import MarketContextReadiness, MarketDirection, MarketRegime, TradePosture
from engines.option_chain_analytics.enums import OptionAnalyticsBias
from engines.price_action.enums import Trend
from engines.strategy_decision_v2 import StrategyAction, StrategyDecisionV2Engine, StrategyDecisionV2Input, StrategySetupStatus
from engines.vwap.levels import VWAPLevels
from tests.test_market_context_v2_integration import NOW, input_bundle


def cam():
    return CamarillaLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 103.0, 106.0, 112.0, 118.0, 97.0, 94.0, 88.0, 82.0)


def cpr():
    return CPRLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 99.0, 101.0, 2.0, 2.0)


def vwap(instrument=Instrument.NIFTY):
    return VWAPLevels(instrument, date(2026, 7, 14), NOW, 100.0, 1000, 100000.0)


def build_stack(kind="bullish"):
    if kind == "bearish":
        context = MarketContextV2Engine(instrument=Instrument.NIFTY).process(input_bundle(Trend.BEARISH, OptionAnalyticsBias.BEARISH, 93.0))
    elif kind == "conflict":
        context = MarketContextV2Engine(instrument=Instrument.NIFTY).process(input_bundle(Trend.BULLISH, OptionAnalyticsBias.BEARISH, 108.0))
    elif kind == "insufficient":
        context = MarketContextV2Engine(instrument=Instrument.NIFTY).process(input_bundle(Trend.BULLISH, OptionAnalyticsBias.BULLISH, 108.0))
        context = type(context)(**{**{field: getattr(context, field) for field in context.__dataclass_fields__}, "direction": MarketDirection.INSUFFICIENT_DATA, "readiness": MarketContextReadiness.INSUFFICIENT, "trade_posture": TradePosture.INSUFFICIENT_DATA, "confidence": 0.0, "primary_sources_available": 0, "bullish_score": 0, "bearish_score": 0, "net_score": 0})
    elif kind == "low_confidence":
        context = MarketContextV2Engine(instrument=Instrument.NIFTY).process(input_bundle(Trend.BULLISH, OptionAnalyticsBias.BULLISH, 108.0))
        context = type(context)(**{**{field: getattr(context, field) for field in context.__dataclass_fields__}, "confidence": 0.2})
    else:
        context = MarketContextV2Engine(instrument=Instrument.NIFTY).process(input_bundle(Trend.BULLISH, OptionAnalyticsBias.BULLISH, 108.0))
    return AIReasoningV2Engine(instrument=Instrument.NIFTY).process(context)


def replace_context(reasoning, **changes):
    context = replace(reasoning.market_context, **changes)
    direction = AIReasoningDirection(context.direction.value)
    state = reasoning.reasoning_state
    if context.trade_posture is TradePosture.WAIT_FOR_CONFIRMATION:
        state = AIReasoningState.WAITING_CONFIRMATION
    return replace(
        reasoning,
        timestamp=context.timestamp,
        market_context=context,
        direction=direction,
        reasoning_state=state,
        confidence=context.confidence,
    )


def test_replace_context_keeps_reasoning_and_context_timestamps_aligned():
    reasoning = build_stack("bullish")
    new_timestamp = reasoning.timestamp.replace(minute=reasoning.timestamp.minute + 1)

    updated = replace_context(
        reasoning,
        timestamp=new_timestamp,
    )

    assert updated.timestamp == new_timestamp
    assert updated.market_context.timestamp == new_timestamp
    assert updated.timestamp == updated.market_context.timestamp
    assert updated.instrument is updated.market_context.instrument
    assert updated.confidence == updated.market_context.confidence


def test_no_network_strategy_decision_flow_and_application_defaults():
    engine = StrategyDecisionV2Engine(instrument=Instrument.NIFTY)
    bullish = engine.process(StrategyDecisionV2Input(build_stack("bullish"), 108.0, cam(), cpr(), vwap()))
    assert bullish.action is StrategyAction.CONSIDER_LONG
    assert bullish.setup_status is StrategySetupStatus.READY_FOR_RISK_REVIEW
    assert bullish.risk_handoff.requires_risk_review is True
    assert bullish.market_context is bullish.ai_reasoning.market_context
    bearish = engine.process(StrategyDecisionV2Input(build_stack("bearish"), 93.0, cam(), cpr(), vwap()))
    assert bearish.action is StrategyAction.CONSIDER_SHORT
    conflict = StrategyDecisionV2Engine(instrument=Instrument.NIFTY).process(StrategyDecisionV2Input(build_stack("conflict"), 108.0, cam(), cpr(), vwap()))
    assert conflict.action is StrategyAction.NO_TRADE
    lifecycle = ApplicationBootstrap().create_application()
    snapshot = lifecycle.snapshot().orchestrator_snapshot
    assert snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert snapshot.broker_mode is BrokerExecutionMode.DRY_RUN
