from application.bootstrap import ApplicationBootstrap
from application.trade_lifecycle_runtime_integration_v1 import (
    TradeLifecycleCoordinatorRegistry,
    TradeLifecyclePositionPriceRequest,
    TradeLifecycleRoutingRequest,
    TradeLifecycleRuntimeIntegrationV1,
    TradeLifecycleRuntimeIntegrationV1Configuration,
)
from core.enums.instrument import Instrument
from engines.position_management_v1 import PositionPriceUpdate
from tests.test_trade_lifecycle_v1_coordinator import coordinator
from tests.test_trade_lifecycle_v1_models import request


def test_trade_lifecycle_runtime_integration_dry_run_flow_end_to_end():
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

    item.start()
    routed = item.route_context(
        TradeLifecycleRoutingRequest(Instrument.NIFTY, request())
    )
    assert routed.coordinator_snapshot.execution_result is not None

    opened = item.confirm_execution_fill(
        instrument=Instrument.NIFTY,
        fill_quantity=2,
        fill_price=108.0,
    )
    position = opened.coordinator_snapshot.position_result.position
    assert position.open_quantity == 2

    priced = item.route_position_price(
        TradeLifecyclePositionPriceRequest(
            Instrument.NIFTY,
            PositionPriceUpdate(Instrument.NIFTY, position.updated_at, 118.0),
        )
    )
    assert priced.coordinator_snapshot.position_snapshot.has_open_position is True

    partial = item.partial_exit_position(
        instrument=Instrument.NIFTY,
        quantity=1,
        exit_price=118.0,
    )
    assert partial.coordinator_snapshot.position_result.position.open_quantity == 1

    closed = item.close_position(instrument=Instrument.NIFTY, exit_price=120.0)
    assert closed.coordinator_snapshot.position_snapshot.has_open_position is False

    stopped = item.stop()
    assert stopped.active_execution_count == 0
    assert stopped.active_position_count == 0
