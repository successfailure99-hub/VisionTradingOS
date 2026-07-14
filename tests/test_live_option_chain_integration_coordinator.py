from application.live_option_chain_integration import (
    LiveOptionChainIntegrationCoordinator,
    LiveOptionChainIntegrationStatus,
)
from application.live_option_chain import LiveOptionChainStatus
from tests.test_live_option_chain_integration_lifecycle import build_stack


def test_initial_validate_snapshot_and_dependency_identity():
    lifecycle, manager, runtime, _engine, _transport, now = build_stack(start_application=True)
    coordinator = LiveOptionChainIntegrationCoordinator(
        lifecycle=lifecycle,
        subscription_manager=manager,
        live_option_chain_runtime=runtime,
        clock=lambda: now,
    )
    assert coordinator.lifecycle is lifecycle
    assert coordinator.subscription_manager is manager
    assert coordinator.live_option_chain_runtime is runtime

    initial = coordinator.snapshot()
    assert initial.status is LiveOptionChainIntegrationStatus.CREATED
    assert initial.ready is False
    assert initial.running is False

    snapshot = coordinator.validate()
    assert snapshot.status is LiveOptionChainIntegrationStatus.READY
    assert snapshot.validation_count == 1
    assert snapshot.ready is True
    assert snapshot.running is False
    assert snapshot.live_option_chain_status is LiveOptionChainStatus.CREATED

    started = coordinator.start()
    assert started.status is LiveOptionChainIntegrationStatus.RUNNING
    assert started.ready is True
    assert started.running is True
    assert started.live_option_chain_status in {
        LiveOptionChainStatus.COLLECTING,
        LiveOptionChainStatus.PARTIAL,
        LiveOptionChainStatus.READY,
        LiveOptionChainStatus.STALE,
    }


def test_stopped_live_option_runtime_is_not_ready_after_validation():
    lifecycle, manager, runtime, _engine, _transport, now = build_stack(start_application=True)
    runtime.start()
    runtime.stop()
    coordinator = LiveOptionChainIntegrationCoordinator(
        lifecycle=lifecycle,
        subscription_manager=manager,
        live_option_chain_runtime=runtime,
        clock=lambda: now,
    )

    snapshot = coordinator.validate()

    assert snapshot.status is LiveOptionChainIntegrationStatus.READY
    assert snapshot.live_option_chain_status is LiveOptionChainStatus.STOPPED
    assert snapshot.ready is False
    assert snapshot.running is False
