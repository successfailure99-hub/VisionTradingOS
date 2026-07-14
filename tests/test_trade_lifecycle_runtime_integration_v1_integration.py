import pytest

from application.bootstrap import ApplicationBootstrap
from application.enums import ExecutionSafetyMode, RuntimeStatus
from application.trade_lifecycle_runtime_integration_v1 import (
    TradeLifecycleCoordinatorRegistry,
    TradeLifecycleRuntimeIntegrationStatus,
    TradeLifecycleRuntimeIntegrationV1,
    TradeLifecycleRuntimeIntegrationV1Configuration,
)
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from tests.test_trade_lifecycle_v1_coordinator import coordinator


def _running_lifecycle():
    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    return lifecycle


def _integration():
    registry = TradeLifecycleCoordinatorRegistry()
    registry.register(Instrument.NIFTY, coordinator())
    return TradeLifecycleRuntimeIntegrationV1(
        application_lifecycle=_running_lifecycle(),
        registry=registry,
        configuration=TradeLifecycleRuntimeIntegrationV1Configuration(
            enabled_instruments=(Instrument.NIFTY,)
        ),
    )


def test_validate_start_stop_and_snapshot_safety_contract():
    item = _integration()

    assert item.snapshot().status is TradeLifecycleRuntimeIntegrationStatus.CREATED
    ready = item.validate()
    assert ready.status is TradeLifecycleRuntimeIntegrationStatus.READY
    assert ready.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert ready.broker_mode is BrokerExecutionMode.DRY_RUN

    running = item.start()
    assert running.status is TradeLifecycleRuntimeIntegrationStatus.RUNNING
    assert running.application_status is RuntimeStatus.RUNNING
    assert running.running_instrument_count == 1
    assert item.start() is not running

    stopped = item.stop()
    assert stopped.status is TradeLifecycleRuntimeIntegrationStatus.STOPPED
    assert item.stop().status is TradeLifecycleRuntimeIntegrationStatus.STOPPED


def test_start_requires_running_application_when_configured():
    registry = TradeLifecycleCoordinatorRegistry()
    registry.register(Instrument.NIFTY, coordinator())
    lifecycle = ApplicationBootstrap().create_application()
    item = TradeLifecycleRuntimeIntegrationV1(
        application_lifecycle=lifecycle,
        registry=registry,
        configuration=TradeLifecycleRuntimeIntegrationV1Configuration(
            enabled_instruments=(Instrument.NIFTY,)
        ),
    )

    with pytest.raises(RuntimeError, match="application lifecycle must be RUNNING"):
        item.start()


def test_validate_requires_registry_to_match_configuration():
    registry = TradeLifecycleCoordinatorRegistry()
    registry.register(Instrument.NIFTY, coordinator())
    item = TradeLifecycleRuntimeIntegrationV1(
        application_lifecycle=_running_lifecycle(),
        registry=registry,
        configuration=TradeLifecycleRuntimeIntegrationV1Configuration(
            enabled_instruments=(Instrument.NIFTY, Instrument.BANKNIFTY)
        ),
    )

    with pytest.raises(ValueError, match="registry instruments"):
        item.validate()


def test_validate_preserves_registry_mismatch_error():
    registry = TradeLifecycleCoordinatorRegistry()
    registry.register(Instrument.NIFTY, coordinator())
    item = TradeLifecycleRuntimeIntegrationV1(
        application_lifecycle=_running_lifecycle(),
        registry=registry,
        configuration=TradeLifecycleRuntimeIntegrationV1Configuration(
            enabled_instruments=(Instrument.NIFTY, Instrument.BANKNIFTY)
        ),
    )

    with pytest.raises(
        ValueError,
        match="registry instruments must match configured instruments",
    ):
        item.validate()

    snapshot = item.snapshot()
    assert snapshot.status is TradeLifecycleRuntimeIntegrationStatus.ERROR
    assert "registry instruments" in snapshot.last_error


def test_snapshot_is_safe_when_registry_is_incomplete():
    registry = TradeLifecycleCoordinatorRegistry()
    registry.register(Instrument.NIFTY, coordinator())
    item = TradeLifecycleRuntimeIntegrationV1(
        application_lifecycle=_running_lifecycle(),
        registry=registry,
        configuration=TradeLifecycleRuntimeIntegrationV1Configuration(
            enabled_instruments=(Instrument.NIFTY, Instrument.BANKNIFTY)
        ),
    )

    snapshot = item.snapshot()

    assert snapshot.configured_instrument_count == 2
    assert tuple(
        instrument_snapshot.instrument for instrument_snapshot in snapshot.instruments
    ) == (Instrument.NIFTY,)
    assert snapshot.ready is False
