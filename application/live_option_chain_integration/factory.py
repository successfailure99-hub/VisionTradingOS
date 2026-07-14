"""
Factory for live option-chain runtime integration.
"""

from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_market_data import LiveMarketDataRuntime
from application.live_option_chain import LiveOptionChainRuntime
from application.live_option_chain_integration.adapters import (
    RawOptionTickBatchDeliveryAdapter,
    UnderlyingPriceDeliveryAdapter,
)
from application.live_option_chain_integration.configuration import (
    LiveOptionChainIntegrationConfiguration,
)
from application.live_option_chain_integration.coordinator import (
    LiveOptionChainIntegrationCoordinator,
)
from brokers.zerodha.option_market_data import ZerodhaOptionMarketDataSubscriptionManager


class LiveOptionChainIntegrationCoordinatorFactory:
    def create(
        self,
        *,
        lifecycle: ApplicationLifecycleManager,
        subscription_manager: ZerodhaOptionMarketDataSubscriptionManager,
        live_option_chain_runtime: LiveOptionChainRuntime,
        live_market_data_runtime: LiveMarketDataRuntime | None = None,
        configuration: LiveOptionChainIntegrationConfiguration | None = None,
        clock=None,
    ) -> LiveOptionChainIntegrationCoordinator:
        return LiveOptionChainIntegrationCoordinator(
            lifecycle=lifecycle,
            subscription_manager=subscription_manager,
            live_option_chain_runtime=live_option_chain_runtime,
            live_market_data_runtime=live_market_data_runtime,
            configuration=configuration,
            clock=clock,
        )

    def create_underlying_price_adapter(
        self,
        coordinator: LiveOptionChainIntegrationCoordinator,
    ) -> UnderlyingPriceDeliveryAdapter:
        return UnderlyingPriceDeliveryAdapter(coordinator)

    def create_option_tick_batch_adapter(
        self,
        coordinator: LiveOptionChainIntegrationCoordinator,
    ) -> RawOptionTickBatchDeliveryAdapter:
        return RawOptionTickBatchDeliveryAdapter(coordinator)
