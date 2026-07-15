from application.trade_journal_runtime_integration_v1 import (
    TradeJournalRuntimeIntegrationV1,
    TradeJournalRuntimeIntegrationV1Factory,
)
from tests.test_trade_journal_runtime_integration_v1_end_to_end import lifecycle_integration, journal_engine


def test_factory_reuses_exact_owners_without_side_effects():
    lifecycle = lifecycle_integration()
    journal = journal_engine()
    integration = TradeJournalRuntimeIntegrationV1Factory().create(
        lifecycle_integration=lifecycle,
        journal_engine=journal,
    )

    assert isinstance(integration, TradeJournalRuntimeIntegrationV1)
    assert integration.lifecycle_integration is lifecycle
    assert integration.journal_engine is journal
    assert journal.snapshot().trade_count == 0
    assert journal.snapshot().running is False
