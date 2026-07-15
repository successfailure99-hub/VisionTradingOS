"""
Factory for Trade Journal Runtime Integration V1.
"""

from application.trade_journal_runtime_integration_v1.configuration import TradeJournalRuntimeIntegrationV1Configuration
from application.trade_journal_runtime_integration_v1.integration import TradeJournalRuntimeIntegrationV1
from application.trade_lifecycle_runtime_integration_v1 import TradeLifecycleRuntimeIntegrationV1
from core.event_bus import EventBus
from engines.trade_journal_v1 import TradeJournalV1Engine


class TradeJournalRuntimeIntegrationV1Factory:
    def create(
        self,
        *,
        lifecycle_integration: TradeLifecycleRuntimeIntegrationV1,
        journal_engine: TradeJournalV1Engine,
        configuration: TradeJournalRuntimeIntegrationV1Configuration | None = None,
        event_bus: EventBus | None = None,
        clock=None,
    ) -> TradeJournalRuntimeIntegrationV1:
        return TradeJournalRuntimeIntegrationV1(
            lifecycle_integration=lifecycle_integration,
            journal_engine=journal_engine,
            configuration=configuration,
            event_bus=event_bus,
            clock=clock,
        )
