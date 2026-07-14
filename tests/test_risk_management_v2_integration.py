from application.bootstrap import ApplicationBootstrap
from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.ai_reasoning_v2 import AIReasoningV2Engine
from engines.market_context_v2 import MarketContextV2Engine
from engines.risk_management_v2 import RiskDecision, RiskManagementV2Engine, RiskStatus
from engines.strategy_decision_v2 import StrategyDecisionV2Engine, StrategyDecisionV2Input
from tests.test_market_context_v2_integration import input_bundle
from tests.test_risk_management_v2_calculator import account, config, exposure, risk_input
from tests.test_strategy_decision_v2_integration import cam, cpr, vwap
from engines.option_chain_analytics.enums import OptionAnalyticsBias
from engines.price_action.enums import Trend


def stack(kind="bullish"):
    trend = Trend.BEARISH if kind == "bearish" else Trend.BULLISH
    bias = OptionAnalyticsBias.BEARISH if kind == "bearish" else OptionAnalyticsBias.BULLISH
    price = 93.0 if kind == "bearish" else 108.0
    context = MarketContextV2Engine(instrument=Instrument.NIFTY).process(input_bundle(trend, bias, price))
    reasoning = AIReasoningV2Engine(instrument=Instrument.NIFTY).process(context)
    return StrategyDecisionV2Engine(instrument=Instrument.NIFTY).process(
        StrategyDecisionV2Input(reasoning, price, cam(), cpr(), vwap())
    )


def test_no_network_risk_flow_approval_reduction_rejection_and_defaults():
    engine = RiskManagementV2Engine(instrument=Instrument.NIFTY, configuration=config())
    long_snapshot = engine.process(risk_input(stack("bullish")))
    short_strategy = stack("bearish")
    short_snapshot = engine.process(risk_input(short_strategy, proposed_entry_price=93.0, proposed_invalidation_price=143.0, proposed_objective_price=13.0))
    reduced = engine.process(
        risk_input(
            stack("bullish"),
            instrument_exposure=exposure(current_notional_exposure=850.0),
            proposed_invalidation_price=83.0,
            proposed_objective_price=148.0,
        )
    )
    rejected = engine.process(risk_input(stack("bullish"), account=account(realized_pnl_today=-300.0)))

    assert long_snapshot.decision is RiskDecision.APPROVED
    assert short_snapshot.decision is RiskDecision.APPROVED
    assert reduced.decision is RiskDecision.APPROVED_REDUCED
    assert rejected.status is RiskStatus.BLOCKED_BY_DAILY_LOSS
    assert long_snapshot.strategy.direction.value == "long"
    assert short_snapshot.strategy.direction.value == "short"
    assert not any("broker" in field or "order" in field for field in long_snapshot.__dataclass_fields__)

    lifecycle = ApplicationBootstrap().create_application()
    application_snapshot = lifecycle.snapshot().orchestrator_snapshot
    assert application_snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert application_snapshot.broker_mode is BrokerExecutionMode.DRY_RUN
