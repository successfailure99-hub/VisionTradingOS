from application.bootstrap import ApplicationBootstrap
from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.ai_reasoning_v2 import AIReasoningV2Engine
from engines.multi_timeframe_evidence_fusion.enums import FusionDirection
from tests.test_ai_reasoning_v2_interpreter import intelligence


def test_no_network_deterministic_intelligence_to_ai_reasoning_v2_flow():
    inputs = intelligence(direction=FusionDirection.BULLISH)
    reasoning = AIReasoningV2Engine(instrument=Instrument.NIFTY).process(
        inputs.multi_timeframe_evidence,
        inputs.market_state,
        inputs.setup_classification,
        inputs.chart_explanation,
    )

    assert reasoning.direction.value == "bullish"
    assert reasoning.multi_timeframe_evidence is inputs.multi_timeframe_evidence
    assert reasoning.market_state is inputs.market_state
    assert reasoning.setup_classification is inputs.setup_classification
    assert reasoning.chart_explanation is inputs.chart_explanation
    assert reasoning.evidence[0].role.value == "primary"
    assert reasoning.evidence[1].role.value == "primary"
    assert reasoning.evidence[2].role.value == "confirmation"
    assert reasoning.actionable_context is True


def test_application_defaults_remain_analysis_only_and_dry_run():
    lifecycle = ApplicationBootstrap().create_application()
    snapshot = lifecycle.snapshot().orchestrator_snapshot
    assert snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert snapshot.broker_mode is BrokerExecutionMode.DRY_RUN
