"""
Small callable adapters for explicit live option-chain delivery.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime

from application.live_option_chain_integration.models import LiveOptionChainDeliveryResult


class UnderlyingPriceDeliveryAdapter:
    def __init__(
        self,
        coordinator: "LiveOptionChainIntegrationCoordinator",
    ):
        self._coordinator = coordinator

    @property
    def coordinator(self):
        return self._coordinator

    def __call__(
        self,
        price: float,
        *,
        timestamp: datetime | None = None,
    ) -> LiveOptionChainDeliveryResult:
        return self._coordinator.deliver_underlying_price(price, timestamp=timestamp)


class RawOptionTickBatchDeliveryAdapter:
    def __init__(
        self,
        coordinator: "LiveOptionChainIntegrationCoordinator",
    ):
        self._coordinator = coordinator

    @property
    def coordinator(self):
        return self._coordinator

    def __call__(
        self,
        raw_ticks: Iterable[Mapping[str, object]],
    ) -> LiveOptionChainDeliveryResult:
        return self._coordinator.deliver_option_ticks(raw_ticks)


from application.live_option_chain_integration.coordinator import LiveOptionChainIntegrationCoordinator
