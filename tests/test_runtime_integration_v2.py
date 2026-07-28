from datetime import timedelta

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.models.tick import Tick
from engines.risk_management_v2 import AccountRiskState, InstrumentExposureState, RiskManagementV2Input, SessionRiskState
from engines.risk_management_v2.enums import RiskDecision
from engines.strategy_decision_v2.enums import StrategyAction
from tests.test_ai_reasoning_v2_models import NOW, explanation, fusion, market_state, setup
from tests.test_strategy_decision_v2_integration import build_stack


def tick(price=100.0, *, timestamp=NOW):
    return Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=price,
        volume=100,
        bid_price=price - 0.1,
        ask_price=price + 0.1,
        open_interest=0,
    )


def runtime():
    item = SymbolRuntime(EventBus(), RuntimeConfiguration(), RuntimeInstrument.NIFTY)
    item.start()
    item._last_tick = tick()
    return item


def test_bullish_runtime_handoff_reaches_risk_lifecycle_paper_and_journal():
    item = runtime()
    paper_calls = []
    original_on_tick = item.paper_trading_engine.on_tick

    def paper_spy(live_tick, *, strategy=None, risk=None):
        paper_calls.append((strategy, risk))
        return original_on_tick(live_tick, strategy=strategy, risk=risk)

    item.paper_trading_engine.on_tick = paper_spy

    reasoning = item.ai_reasoning_v2_engine.process(
        fusion(timestamp=NOW),
        market_state(timestamp=NOW),
        setup(timestamp=NOW),
        explanation(timestamp=NOW),
        timestamp=NOW,
    )
    item._process_v2_execution_chain(reasoning)
    lifecycle_timestamp = item.trade_lifecycle_v1.snapshot().timestamp
    item._process_paper_tick(tick(101.0, timestamp=lifecycle_timestamp + timedelta(seconds=1)))

    snapshot = item.snapshot()
    assert snapshot.ai_reasoning_v2 is not None
    assert snapshot.strategy_decision_v2.action is StrategyAction.CONSIDER_LONG
    assert snapshot.risk_management_v2.decision in {RiskDecision.APPROVED, RiskDecision.APPROVED_REDUCED}
    assert snapshot.trade_lifecycle_v1.execution_result is not None
    assert snapshot.trade_lifecycle_v1.position_snapshot.has_open_position is True
    assert snapshot.trade_journal_v1.ready is True
    assert snapshot.decision_audit.rejected is False
    assert paper_calls
    assert paper_calls[-1][0] is snapshot.strategy_decision_v2
    assert paper_calls[-1][1] is snapshot.risk_management_v2


def test_conflict_runtime_handoff_records_strategy_rejection_reason():
    item = runtime()

    item._process_v2_execution_chain(build_stack("conflict"))

    snapshot = item.snapshot()
    assert snapshot.strategy_decision_v2.action is StrategyAction.NO_TRADE
    assert snapshot.risk_management_v2 is None
    assert snapshot.decision_audit.rejected is True
    assert snapshot.decision_audit.rejected_at == "Strategy"
    assert snapshot.decision_audit.strategy_decision_v2 is snapshot.strategy_decision_v2
    assert snapshot.decision_audit.reason


def test_risk_rejection_is_visible_without_strategy_rule_changes():
    item = runtime()

    def rejected_risk_input(strategy):
        entry = 100.0
        return RiskManagementV2Input(
            strategy=strategy,
            account=AccountRiskState(strategy.timestamp, 100000.0, 100000.0, 100000.0, 100000.0, 0.0, 0.0, 0.0),
            session=SessionRiskState(strategy.timestamp.date(), 0, 0, 0, 0, 0.0),
            instrument_exposure=InstrumentExposureState(strategy.instrument, 0, 0.0, 0.0),
            proposed_entry_price=entry,
            proposed_invalidation_price=99.0,
            proposed_objective_price=None,
        )

    item._build_risk_management_v2_input = rejected_risk_input

    item._process_v2_execution_chain(build_stack("bullish"))

    snapshot = item.snapshot()
    assert snapshot.strategy_decision_v2.action is StrategyAction.CONSIDER_LONG
    assert snapshot.risk_management_v2.decision is RiskDecision.REJECTED
    assert snapshot.trade_lifecycle_v1.processing_count == 0
    assert snapshot.decision_audit.rejected is True
    assert snapshot.decision_audit.rejected_at == "Risk"
    assert "Structural objective is required" in snapshot.decision_audit.reason
