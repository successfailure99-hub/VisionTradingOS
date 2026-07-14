from application.option_chain_analytics_integration import (
    OptionChainAnalyticsIntegrationCoordinator,
    OptionChainAnalyticsIntegrationCoordinatorFactory,
)
from tests.test_option_chain_analytics_integration_processing import build_running_stack


def test_factory_reuses_owners_and_adapter():
    stack = build_running_stack(start_analytics=False)
    factory = OptionChainAnalyticsIntegrationCoordinatorFactory()
    coordinator = factory.create(
        lifecycle=stack["lifecycle"],
        live_option_chain_integration=stack["live_coordinator"],
        analytics_engine=stack["analytics_engine"],
        clock=lambda: __import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    assert isinstance(coordinator, OptionChainAnalyticsIntegrationCoordinator)
    assert coordinator.lifecycle is stack["lifecycle"]
    assert coordinator.live_option_chain_integration is stack["live_coordinator"]
    assert coordinator.analytics_engine is stack["analytics_engine"]
    assert factory.create_delivery_adapter(coordinator).coordinator is coordinator
