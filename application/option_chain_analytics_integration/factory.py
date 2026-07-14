"""
Factory for option-chain analytics runtime integration.
"""

from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_option_chain_integration import LiveOptionChainIntegrationCoordinator
from application.option_chain_analytics_integration.adapters import (
    OptionChainAnalyticsSnapshotDeliveryAdapter,
)
from application.option_chain_analytics_integration.configuration import (
    OptionChainAnalyticsIntegrationConfiguration,
)
from application.option_chain_analytics_integration.coordinator import (
    OptionChainAnalyticsIntegrationCoordinator,
)
from engines.option_chain_analytics import OptionChainAnalyticsEngine


class OptionChainAnalyticsIntegrationCoordinatorFactory:
    def create(
        self,
        *,
        lifecycle: ApplicationLifecycleManager,
        live_option_chain_integration: LiveOptionChainIntegrationCoordinator,
        analytics_engine: OptionChainAnalyticsEngine,
        configuration: OptionChainAnalyticsIntegrationConfiguration | None = None,
        clock=None,
    ) -> OptionChainAnalyticsIntegrationCoordinator:
        return OptionChainAnalyticsIntegrationCoordinator(
            lifecycle=lifecycle,
            live_option_chain_integration=live_option_chain_integration,
            analytics_engine=analytics_engine,
            configuration=configuration,
            clock=clock,
        )

    def create_delivery_adapter(
        self,
        coordinator: OptionChainAnalyticsIntegrationCoordinator,
    ) -> OptionChainAnalyticsSnapshotDeliveryAdapter:
        return OptionChainAnalyticsSnapshotDeliveryAdapter(coordinator)
