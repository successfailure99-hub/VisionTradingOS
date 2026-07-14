from application.bootstrap import ApplicationBootstrap
from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.ai_reasoning_v2 import AIReasoningV2Engine
from engines.market_context_v2 import MarketContextV2Engine
from engines.market_context_v2.enums import MarketDirection, TradePosture
from tests.test_market_context_v2_integration import input_bundle
from engines.option_chain_analytics.enums import OptionAnalyticsBias
from engines.price_action.enums import Trend


def test_no_network_market_context_v2_to_ai_reasoning_v2_flow():
    context_engine = MarketContextV2Engine(instrument=Instrument.NIFTY)
    context = context_engine.process(
        input_bundle(Trend.BULLISH, OptionAnalyticsBias.BULLISH, 108.0)
    )
    reasoning = AIReasoningV2Engine(instrument=Instrument.NIFTY).process(context)
    assert reasoning.direction.value == context.direction.value
    assert reasoning.market_context is context
    assert reasoning.evidence[0].role.value == "primary"
    assert reasoning.evidence[1].role.value == "primary"
    assert reasoning.evidence[2].role.value == "confirmation"
    assert reasoning.actionable_context is True
    assert context.direction in {MarketDirection.BULLISH, MarketDirection.STRONGLY_BULLISH}
    assert context.trade_posture is TradePosture.LOOK_FOR_LONGS


def test_application_defaults_remain_analysis_only_and_dry_run():
    lifecycle = ApplicationBootstrap().create_application()
    snapshot = lifecycle.snapshot().orchestrator_snapshot
    assert snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert snapshot.broker_mode is BrokerExecutionMode.DRY_RUN
