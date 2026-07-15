from threading import RLock

from application.trade_journal_runtime_integration_v1 import (
    TradeJournalRuntimeIntegrationStatus,
)
from tests.test_trade_journal_runtime_integration_v1_end_to_end import integration_stack


def test_constructor_validate_start_stop_clear_and_rlock():
    integration, lifecycle_integration, journal = integration_stack()

    assert integration.lifecycle_integration is lifecycle_integration
    assert integration.journal_engine is journal
    assert integration.snapshot().status is TradeJournalRuntimeIntegrationStatus.CREATED
    assert integration.validate().status is TradeJournalRuntimeIntegrationStatus.READY
    assert integration.start().status is TradeJournalRuntimeIntegrationStatus.RUNNING
    assert integration.start().status is TradeJournalRuntimeIntegrationStatus.RUNNING
    assert isinstance(integration._lock, RLock().__class__)
    assert integration.stop().status is TradeJournalRuntimeIntegrationStatus.STOPPED
    assert integration.stop().status is TradeJournalRuntimeIntegrationStatus.STOPPED
    assert integration.clear().status is TradeJournalRuntimeIntegrationStatus.CLEARED
