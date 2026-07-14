from dataclasses import replace

import pytest

from application.bootstrap import ApplicationBootstrap
from application.trade_lifecycle_runtime_integration_v1 import (
    TradeLifecycleCoordinatorRegistry,
    TradeLifecyclePositionPriceRequest,
    TradeLifecycleRoutingRequest,
    TradeLifecycleRoutingResult,
    TradeLifecycleRuntimeIntegrationV1,
    TradeLifecycleRuntimeIntegrationV1Configuration,
)
from core.enums.instrument import Instrument
from engines.position_management_v1 import PositionPriceUpdate
from tests.test_market_context_v2_integration import input_bundle
from tests.test_strategy_decision_v2_integration import cam, cpr, vwap
from tests.test_trade_lifecycle_v1_coordinator import coordinator
from tests.test_trade_lifecycle_v1_models import request
from engines.market_context_v2 import MarketContextV2Engine
from engines.market_context_v2 import (
    MarketContextReadiness,
    MarketDirection,
    TradePosture,
)
from engines.option_chain_analytics.enums import OptionAnalyticsBias
from engines.price_action.enums import Trend


def _running_integration():
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
    return item


def _routing_request(lifecycle_request=None):
    return TradeLifecycleRoutingRequest(
        instrument=Instrument.NIFTY,
        lifecycle_request=lifecycle_request or request(),
    )


def test_route_context_processes_once_and_publishes_dashboard_snapshot():
    item = _running_integration()
    snapshot = item.route_context(_routing_request())

    assert snapshot.instrument is Instrument.NIFTY
    assert snapshot.last_routing_result is TradeLifecycleRoutingResult.PROCESSED
    assert snapshot.context_process_count == 1
    assert item.snapshot().routing_count == 1
    assert item.snapshot().active_execution_count == 1


def test_duplicate_context_after_trade_creation_is_rejected():
    item = _running_integration()
    routing_request = _routing_request()
    item.route_context(routing_request)

    with pytest.raises(RuntimeError, match="duplicate trade creation request"):
        item.route_context(routing_request)


def test_insufficient_data_context_is_reported_without_execution():
    item = _running_integration()
    source_context = MarketContextV2Engine(instrument=Instrument.NIFTY).process(
        input_bundle(Trend.RANGE, OptionAnalyticsBias.NEUTRAL, 108.0)
    )
    sparse_context = replace(
        source_context,
        direction=MarketDirection.INSUFFICIENT_DATA,
        readiness=MarketContextReadiness.INSUFFICIENT,
        trade_posture=TradePosture.INSUFFICIENT_DATA,
        confidence=0.0,
        primary_sources_available=0,
        bullish_score=0,
        bearish_score=0,
        net_score=0,
    )
    lifecycle_request = replace(
        request(),
        market_context=sparse_context,
        camarilla=cam(),
        cpr=cpr(),
        vwap=vwap(),
    )

    snapshot = item.route_context(_routing_request(lifecycle_request))

    assert snapshot.last_routing_result is TradeLifecycleRoutingResult.INSUFFICIENT_DATA
    assert item.snapshot().active_execution_count == 0
    assert item.snapshot().active_position_count == 0


def test_route_position_price_updates_open_position_and_suppresses_duplicate():
    item = _running_integration()
    item.route_context(_routing_request())
    opened = item.confirm_execution_fill(
        instrument=Instrument.NIFTY,
        fill_quantity=2,
        fill_price=108.0,
    )
    position = opened.coordinator_snapshot.position_result.position
    update = PositionPriceUpdate(Instrument.NIFTY, position.updated_at, 109.0)
    request_ = TradeLifecyclePositionPriceRequest(Instrument.NIFTY, update)

    first = item.route_position_price(request_)
    second = item.route_position_price(request_)

    assert first.price_update_count == 1
    assert second is first
    assert item.snapshot().duplicate_count == 0
