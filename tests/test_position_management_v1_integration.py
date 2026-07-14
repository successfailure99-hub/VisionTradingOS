from datetime import timedelta

from application.bootstrap import ApplicationBootstrap
from application.enums import ExecutionSafetyMode
from application.execution_runtime_v1 import ExecutionFillPolicy, ExecutionRuntimeV1, ExecutionRuntimeV1Configuration
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.position_management_v1 import PositionChange, PositionManagementV1Engine, PositionPriceUpdate
from tests.test_position_management_v1_models import filled_execution
from tests.test_risk_management_v2_calculator import calculate, risk_input, strategy


def test_no_network_execution_to_position_profit_objective_partial_and_close_flow():
    execution = filled_execution()
    engine = PositionManagementV1Engine(instrument=Instrument.NIFTY)
    opened = engine.open_from_execution(execution)
    position = opened.position
    profit = engine.update_price(PositionPriceUpdate(Instrument.NIFTY, position.updated_at + timedelta(minutes=1), position.average_entry_price + 10))
    objective = engine.update_price(PositionPriceUpdate(Instrument.NIFTY, profit.position.updated_at + timedelta(minutes=1), position.objective_price))
    partial = engine.partial_exit(quantity=1, exit_price=position.objective_price)
    closed = engine.close(exit_price=position.objective_price)

    assert opened.position.open_quantity == execution.filled_quantity
    assert profit.position.unrealized_pnl > 0
    assert objective.change is PositionChange.OBJECTIVE_REACHED
    assert partial.position.closed_quantity > 0
    assert closed.position.realized_pnl > 0
    assert engine.snapshot().has_open_position is False


def test_short_position_and_application_defaults_remain_safe():
    risk = calculate(risk_input(strategy("bearish"), proposed_entry_price=93.0, proposed_invalidation_price=143.0, proposed_objective_price=13.0))
    runtime = ExecutionRuntimeV1(
        instrument=Instrument.NIFTY,
        configuration=ExecutionRuntimeV1Configuration(fill_policy=ExecutionFillPolicy.IMMEDIATE_FULL, require_manual_fill_confirmation=True),
    )
    runtime.start()
    execution = runtime.submit(risk)
    engine = PositionManagementV1Engine(instrument=Instrument.NIFTY)
    opened = engine.open_from_execution(execution)
    profit = engine.update_price(PositionPriceUpdate(Instrument.NIFTY, opened.position.updated_at + timedelta(minutes=1), opened.position.average_entry_price - 10))

    assert profit.position.unrealized_pnl > 0
    lifecycle = ApplicationBootstrap().create_application()
    app_snapshot = lifecycle.snapshot().orchestrator_snapshot
    assert app_snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert app_snapshot.broker_mode is BrokerExecutionMode.DRY_RUN
