from application.enums import ExecutionSafetyMode
from application.trade_lifecycle_runtime_integration_v1 import TradeLifecycleRuntimeIntegrationV1
from brokers.zerodha.enums import BrokerExecutionMode
from tests.test_trade_journal_runtime_integration_v1_end_to_end import integration_stack


def test_safety_broker_lifecycle_and_journal_ownership_are_preserved():
    integration, lifecycle_integration, journal = integration_stack()

    assert isinstance(lifecycle_integration, TradeLifecycleRuntimeIntegrationV1)
    assert integration.snapshot().safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert integration.snapshot().broker_mode is BrokerExecutionMode.DRY_RUN
    integration.start()
    assert journal.snapshot().running is True
    integration.stop()
    assert journal.snapshot().running is False
    assert lifecycle_integration.snapshot().running is True
