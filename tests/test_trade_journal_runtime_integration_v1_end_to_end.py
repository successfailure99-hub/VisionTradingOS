from application.bootstrap import ApplicationBootstrap
from application.execution_runtime_v1 import ExecutionRuntimeV1
from application.trade_journal_runtime_integration_v1 import (
    TradeJournalRuntimeIntegrationV1,
    TradeJournalRuntimeIntegrationV1Configuration,
    TradeJournalRoutingResult,
)
from application.trade_lifecycle_runtime_integration_v1 import (
    TradeLifecycleCoordinatorRegistry,
    TradeLifecycleRuntimeIntegrationV1,
    TradeLifecycleRuntimeIntegrationV1Configuration,
)
from application.trade_lifecycle_v1 import TradeLifecycleCoordinatorV1
from core.enums.instrument import Instrument
from engines.ai_reasoning_v2 import AIReasoningV2Engine
from engines.position_management_v1 import PositionManagementV1Engine
from engines.risk_management_v2 import RiskManagementV2Configuration, RiskManagementV2Engine
from engines.strategy_decision_v2 import StrategyDecisionV2Engine
from engines.trade_journal_v1 import TradeJournalV1Engine
from tests.test_trade_journal_v1_integration import closed_lifecycle, open_lifecycle


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


def lifecycle_integration(instrument=Instrument.NIFTY):
    app = ApplicationBootstrap().create_application()
    app.start()
    registry = TradeLifecycleCoordinatorRegistry()
    registry.register(instrument, coordinator(instrument))
    item = TradeLifecycleRuntimeIntegrationV1(
        application_lifecycle=app,
        registry=registry,
        configuration=TradeLifecycleRuntimeIntegrationV1Configuration(enabled_instruments=(instrument,)),
    )
    item.start()
    return item


def journal_engine():
    return TradeJournalV1Engine()


def integration_stack(instrument=Instrument.NIFTY):
    lifecycle = lifecycle_integration(instrument)
    journal = journal_engine()
    integration = TradeJournalRuntimeIntegrationV1(
        lifecycle_integration=lifecycle,
        journal_engine=journal,
        configuration=TradeJournalRuntimeIntegrationV1Configuration(enabled_instruments=(instrument,)),
    )
    return integration, lifecycle, journal


def test_no_network_trade_journal_runtime_integration_records_and_aggregates():
    integration = integration_stack()[0]
    integration.start()

    outcome = integration.route_if_closed(closed_lifecycle(exit_price=120.0))
    duplicate = integration.route_if_closed(outcome.lifecycle_snapshot)

    assert outcome.result is TradeJournalRoutingResult.RECORDED
    assert duplicate.result is TradeJournalRoutingResult.DUPLICATE
    snapshot = integration.snapshot()
    assert snapshot.recorded_count == 1
    assert snapshot.duplicate_count == 1
    assert snapshot.journal_snapshot.trade_count == 1
    assert snapshot.analytics_snapshot.overall.win_count == 1
    assert snapshot.instruments[0].recorded_count == 1
