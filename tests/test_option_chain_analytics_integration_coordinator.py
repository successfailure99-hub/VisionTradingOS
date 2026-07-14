from application.option_chain_analytics_integration import (
    OptionChainAnalyticsIntegrationCoordinator,
    OptionChainAnalyticsIntegrationStatus,
)
from tests.test_option_chain_analytics_integration_processing import build_running_stack


def test_initial_validate_snapshot_and_dependencies():
    stack = build_running_stack(start_analytics=False)
    coordinator = stack["analytics_coordinator"]
    assert coordinator.lifecycle is stack["lifecycle"]
    assert coordinator.live_option_chain_integration is stack["live_coordinator"]
    assert coordinator.analytics_engine is stack["analytics_engine"]
    assert coordinator.snapshot().status is OptionChainAnalyticsIntegrationStatus.CREATED
    snapshot = coordinator.validate()
    assert snapshot.status is OptionChainAnalyticsIntegrationStatus.READY
    assert snapshot.ready is True
    assert snapshot.validation_count == 1
