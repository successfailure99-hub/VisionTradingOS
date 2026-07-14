from application.live_option_chain_integration import (
    LiveOptionChainIntegrationCoordinator,
    LiveOptionChainIntegrationCoordinatorFactory,
)
from tests.test_live_option_chain_integration_lifecycle import build_stack


def test_factory_reuses_owners_and_creates_adapters_without_starting():
    lifecycle, manager, runtime, _engine, transport, now = build_stack(start_application=True)
    factory = LiveOptionChainIntegrationCoordinatorFactory()
    coordinator = factory.create(
        lifecycle=lifecycle,
        subscription_manager=manager,
        live_option_chain_runtime=runtime,
        clock=lambda: now,
    )
    assert isinstance(coordinator, LiveOptionChainIntegrationCoordinator)
    assert coordinator.lifecycle is lifecycle
    assert coordinator.subscription_manager is manager
    assert coordinator.live_option_chain_runtime is runtime
    price_adapter = factory.create_underlying_price_adapter(coordinator)
    batch_adapter = factory.create_option_tick_batch_adapter(coordinator)
    assert price_adapter.coordinator is coordinator
    assert batch_adapter.coordinator is coordinator
    assert not any(call[0] == "connect" for call in transport.calls)
    assert coordinator.snapshot().start_count == 0
