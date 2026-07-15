from datetime import date

from application.execution_runtime_v1 import ExecutionRuntimeV1
from application.trade_lifecycle_v1 import TradeLifecycleCoordinatorV1, TradeLifecycleV1Request
from core.enums.instrument import Instrument
from engines.ai_reasoning_v2 import AIReasoningV2Engine
from engines.market_context_v2 import MarketContextV2Engine
from engines.option_chain_analytics.enums import OptionAnalyticsBias
from engines.position_management_v1 import PositionManagementV1Engine
from engines.price_action.enums import Trend
from engines.risk_management_v2 import (
    AccountRiskState,
    InstrumentExposureState,
    RiskManagementV2Configuration,
    RiskManagementV2Engine,
    SessionRiskState,
)
from engines.strategy_decision_v2 import StrategyDecisionV2Engine
from engines.trade_journal_v1 import TradeJournalV1Engine, TradeOutcome, TradeRecordStatus
from tests.test_market_context_v2_integration import NOW, input_bundle
from tests.test_strategy_decision_v2_integration import cam, cpr, vwap


def lifecycle_request(instrument=Instrument.NIFTY):
    context = MarketContextV2Engine(instrument=instrument).process(
        input_bundle(Trend.BULLISH, OptionAnalyticsBias.BULLISH, 108.0)
    )
    return TradeLifecycleV1Request(
        market_context=context,
        current_price=108.0,
        account_risk_state=AccountRiskState(NOW, 10000.0, 10000.0, 10000.0, 10000.0, 0.0, 0.0, 0.0),
        session_risk_state=SessionRiskState(date(2026, 7, 14), 0, 0, 0, 0, 0.0),
        instrument_exposure_state=InstrumentExposureState(instrument, 0, 0.0, 0.0),
        proposed_entry_price=108.0,
        proposed_invalidation_price=83.0,
        proposed_objective_price=148.0,
        camarilla=cam(),
        cpr=cpr(),
        vwap=vwap(instrument),
    )


def coordinator(instrument=Instrument.NIFTY):
    return TradeLifecycleCoordinatorV1(
        instrument=instrument,
        ai_reasoning_engine=AIReasoningV2Engine(instrument=instrument),
        strategy_engine=StrategyDecisionV2Engine(instrument=instrument),
        risk_engine=RiskManagementV2Engine(
            instrument=instrument,
            configuration=RiskManagementV2Configuration(maximum_position_quantity=10),
        ),
        execution_runtime=ExecutionRuntimeV1(instrument=instrument),
        position_engine=PositionManagementV1Engine(instrument=instrument),
    )


def open_lifecycle(instrument=Instrument.NIFTY):
    item = coordinator(instrument)
    item.start()
    item.process(lifecycle_request(instrument))
    return item.confirm_execution_fill(fill_quantity=2, fill_price=108.0)


def closed_lifecycle(exit_price=120.0, instrument=Instrument.NIFTY):
    item = coordinator(instrument)
    item.start()
    item.process(lifecycle_request(instrument))
    item.confirm_execution_fill(fill_quantity=2, fill_price=108.0)
    return item.close_position(exit_price=exit_price)


def test_no_network_trade_journal_v1_records_closed_lifecycle():
    engine = TradeJournalV1Engine()
    engine.start()

    result = engine.record(closed_lifecycle(exit_price=120.0))

    assert result.status is TradeRecordStatus.RECORDED
    assert result.entry.outcome is TradeOutcome.WIN
    assert result.entry.realized_pnl > 0.0
    assert result.entry.r_multiple > 0.0
    assert engine.analytics_snapshot().overall.trade_count == 1
