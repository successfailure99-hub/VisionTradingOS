import pytest

from application.bootstrap import ApplicationBootstrap
from application.trade_lifecycle_runtime_integration_v1 import (
    TradeLifecycleCoordinatorRegistry,
    TradeLifecycleRoutingRequest,
    TradeLifecycleRuntimeIntegrationStatus,
    TradeLifecycleRuntimeIntegrationV1,
    TradeLifecycleRuntimeIntegrationV1Configuration,
)
from core.enums.instrument import Instrument
from tests.test_trade_lifecycle_v1_coordinator import coordinator
from tests.test_trade_lifecycle_v1_models import request


def _integration():
    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    registry = TradeLifecycleCoordinatorRegistry()
    registry.register(Instrument.NIFTY, coordinator())
    item = TradeLifecycleRuntimeIntegrationV1(
        application_lifecycle=lifecycle,
        registry=registry,
        configuration=TradeLifecycleRuntimeIntegrationV1Configuration(
            enabled_instruments=(Instrument.NIFTY,)
        ),
    )
    return item


def test_processing_is_blocked_unless_running():
    item = _integration()
    routing_request = TradeLifecycleRoutingRequest(Instrument.NIFTY, request())

    with pytest.raises(RuntimeError, match="must be running"):
        item.route_context(routing_request)

    item.start()
    assert item.route_context(routing_request).context_process_count == 1


def test_stop_is_blocked_by_active_execution_or_position():
    item = _integration()
    item.start()
    item.route_context(TradeLifecycleRoutingRequest(Instrument.NIFTY, request()))

    with pytest.raises(RuntimeError, match="active execution or position"):
        item.stop()


def test_clear_requires_stopped_inactive_runtime_and_resets_history():
    item = _integration()
    item.start()
    item.stop()
    assert item.history()

    cleared = item.clear()

    assert cleared.status is TradeLifecycleRuntimeIntegrationStatus.CLEARED
    assert item.history() == ()
    with pytest.raises(RuntimeError, match="stopped"):
        item.clear()
