"""
Adapters for option-chain analytics runtime integration.
"""

from application.live_option_chain import LiveOptionChainStatus
from application.live_option_chain_integration import LiveOptionChainIntegrationSnapshot
from application.option_chain_analytics_integration.models import (
    OptionChainAnalyticsProcessingOutcome,
)
from engines.option_chain.models import OptionChainSnapshot, OptionChainState


def analytics_input_from_live_integration_snapshot(
    snapshot: LiveOptionChainIntegrationSnapshot,
) -> tuple[OptionChainSnapshot, OptionChainState]:
    if not isinstance(snapshot, LiveOptionChainIntegrationSnapshot):
        raise TypeError("snapshot must be LiveOptionChainIntegrationSnapshot")
    if snapshot.live_option_chain_status is not LiveOptionChainStatus.READY:
        raise ValueError("live option-chain snapshot must be READY")
    source_snapshot = snapshot.option_chain.latest_option_chain_snapshot
    source_analysis = snapshot.option_chain.latest_option_chain_analysis
    if source_snapshot is None:
        raise ValueError("live integration snapshot has no source OptionChainSnapshot")
    if source_analysis is None:
        raise ValueError("live integration snapshot has no OptionChainState")
    if not isinstance(source_snapshot, OptionChainSnapshot):
        raise TypeError("source snapshot must be OptionChainSnapshot")
    if not isinstance(source_analysis, OptionChainState):
        raise TypeError("source analysis must be OptionChainState")
    if source_snapshot.timestamp != source_analysis.timestamp:
        raise ValueError("source snapshot and analysis timestamps must match")
    if source_snapshot.symbol != snapshot.underlying.value or source_analysis.symbol != snapshot.underlying.value:
        raise ValueError("source underlying does not match live integration context")
    if source_snapshot.expiry_date != snapshot.expiry or source_analysis.expiry_date != snapshot.expiry:
        raise ValueError("source expiry does not match live integration context")
    return source_snapshot, source_analysis


class OptionChainAnalyticsSnapshotDeliveryAdapter:
    def __init__(
        self,
        coordinator: "OptionChainAnalyticsIntegrationCoordinator",
    ):
        self._coordinator = coordinator

    @property
    def coordinator(self):
        return self._coordinator

    def __call__(
        self,
        snapshot: LiveOptionChainIntegrationSnapshot,
    ) -> OptionChainAnalyticsProcessingOutcome:
        return self._coordinator.process_live_snapshot(snapshot)


from application.option_chain_analytics_integration.coordinator import OptionChainAnalyticsIntegrationCoordinator
