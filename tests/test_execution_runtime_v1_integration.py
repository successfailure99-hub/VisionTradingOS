from application.bootstrap import ApplicationBootstrap
from application.enums import ExecutionSafetyMode
from application.execution_runtime_v1 import ExecutionRuntimeV1
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.risk_management_v2 import RiskDecision, RiskManagementV2Engine
from tests.test_risk_management_v2_calculator import account, config, exposure, risk_input, strategy


def test_no_network_strategy_risk_execution_flow_and_application_defaults():
    risk_engine = RiskManagementV2Engine(instrument=Instrument.NIFTY, configuration=config())
    approved = risk_engine.process(risk_input(strategy(), proposed_invalidation_price=83.0, proposed_objective_price=148.0))
    rejected = risk_engine.process(risk_input(strategy(minutes=1), account=account(strategy(minutes=1), realized_pnl_today=-300.0)))
    reduced = risk_engine.process(
        risk_input(
            strategy(minutes=2),
            instrument_exposure=exposure(current_notional_exposure=850.0),
            proposed_invalidation_price=83.0,
            proposed_objective_price=148.0,
        )
    )
    runtime = ExecutionRuntimeV1(instrument=Instrument.NIFTY)
    runtime.start()
    submitted = runtime.submit(approved)
    assert submitted.intent.side.value == "buy"
    assert submitted.intent.quantity == approved.approved_quantity
    partial = runtime.confirm_fill(fill_quantity=1, fill_price=approved.entry_price)
    runtime.confirm_fill(fill_quantity=partial.remaining_quantity, fill_price=approved.entry_price)
    assert runtime.submit(rejected).decision.value == "rejected"
    assert reduced.decision is RiskDecision.APPROVED_REDUCED
    reduced_runtime = ExecutionRuntimeV1(instrument=Instrument.NIFTY)
    reduced_runtime.start()
    reduced_result = reduced_runtime.submit(reduced)
    assert reduced_result.intent.quantity == reduced.approved_quantity

    lifecycle = ApplicationBootstrap().create_application()
    application_snapshot = lifecycle.snapshot().orchestrator_snapshot
    assert application_snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert application_snapshot.broker_mode is BrokerExecutionMode.DRY_RUN
