from application.execution_runtime_v1 import ExecutionRuntimeV1
from application.trade_lifecycle_v1 import TradeLifecycleCoordinatorV1, TradeLifecycleV1Request
from core.enums.instrument import Instrument
from engines.position_management_v1 import PositionManagementV1Engine
from engines.trade_journal_v1 import TradeJournalV1Engine, TradeOutcome, TradeRecordStatus
from tests.test_ai_reasoning_v2_models import NOW
from tests.test_risk_management_v2_calculator import calculate, config, risk_input


def lifecycle_request(instrument=Instrument.NIFTY):
    risk = calculate(
        risk_input(
            proposed_invalidation_price=83.0,
            proposed_objective_price=148.0,
        ),
        configuration=config(maximum_position_quantity=10),
    )
    if risk.instrument is not instrument:
        raise ValueError("test helper currently supports NIFTY lifecycle fixtures")
    return TradeLifecycleV1Request(
        strategy_decision=risk.strategy,
        risk_decision=risk,
    )


def coordinator(instrument=Instrument.NIFTY):
    return TradeLifecycleCoordinatorV1(
        instrument=instrument,
        execution_runtime=ExecutionRuntimeV1(instrument=instrument),
        position_engine=PositionManagementV1Engine(instrument=instrument),
    )


def open_lifecycle(instrument=Instrument.NIFTY):
    item = coordinator(instrument)
    item.start()
    item.process(lifecycle_request(instrument))
    return item.confirm_execution_fill(fill_quantity=1, fill_price=108.0)


def closed_lifecycle(exit_price=120.0, instrument=Instrument.NIFTY):
    item = coordinator(instrument)
    item.start()
    item.process(lifecycle_request(instrument))
    item.confirm_execution_fill(fill_quantity=1, fill_price=108.0)
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
