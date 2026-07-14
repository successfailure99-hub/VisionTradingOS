from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from application.enums import ExecutionSafetyMode, RuntimeStatus
from application.trade_lifecycle_runtime_integration_v1 import (
    TradeLifecycleInstrumentIntegrationSnapshot,
    TradeLifecycleIntegrationChange,
    TradeLifecyclePositionPriceRequest,
    TradeLifecycleRoutingRequest,
    TradeLifecycleRoutingResult,
    TradeLifecycleRuntimeIntegrationStatus,
    TradeLifecycleRuntimeIntegrationV1Snapshot,
)
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.position_management_v1 import PositionPriceUpdate
from tests.test_trade_lifecycle_v1_coordinator import coordinator
from tests.test_trade_lifecycle_v1_models import request

NOW = datetime(2026, 7, 14, 9, 30, tzinfo=timezone.utc)


def test_routing_and_price_requests_are_immutable_and_instrument_safe():
    lifecycle_request = request()
    routing_request = TradeLifecycleRoutingRequest(
        instrument=Instrument.NIFTY,
        lifecycle_request=lifecycle_request,
    )
    price_request = TradeLifecyclePositionPriceRequest(
        instrument=Instrument.NIFTY,
        update=PositionPriceUpdate(Instrument.NIFTY, NOW, 109.0),
    )

    assert routing_request.lifecycle_request is lifecycle_request
    assert price_request.update.market_price == 109.0
    with pytest.raises(FrozenInstanceError):
        routing_request.instrument = Instrument.BANKNIFTY
    with pytest.raises(ValueError, match="routing instrument"):
        TradeLifecycleRoutingRequest(
            instrument=Instrument.BANKNIFTY,
            lifecycle_request=lifecycle_request,
        )
    with pytest.raises(ValueError, match="price update instrument"):
        TradeLifecyclePositionPriceRequest(
            instrument=Instrument.BANKNIFTY,
            update=PositionPriceUpdate(Instrument.NIFTY, NOW, 109.0),
        )


def test_snapshot_models_are_immutable_and_validate_counts():
    coordinator_snapshot = coordinator().snapshot()
    instrument_snapshot = TradeLifecycleInstrumentIntegrationSnapshot(
        instrument=Instrument.NIFTY,
        coordinator_snapshot=coordinator_snapshot,
        routing_count=1,
        context_process_count=1,
        price_update_count=0,
        duplicate_count=0,
        blocked_count=0,
        rejected_count=0,
        error_count=0,
        last_routed_at=NOW,
        last_routing_result=TradeLifecycleRoutingResult.PROCESSED,
        last_error=None,
    )
    snapshot = TradeLifecycleRuntimeIntegrationV1Snapshot(
        timestamp=NOW,
        status=TradeLifecycleRuntimeIntegrationStatus.READY,
        change=TradeLifecycleIntegrationChange.VALIDATED,
        application_status=RuntimeStatus.RUNNING,
        safety_mode=ExecutionSafetyMode.ANALYSIS_ONLY,
        broker_mode=BrokerExecutionMode.DRY_RUN,
        instruments=(instrument_snapshot,),
        configured_instrument_count=1,
        ready_instrument_count=1,
        running_instrument_count=0,
        active_execution_count=0,
        active_position_count=0,
        validation_count=1,
        start_count=0,
        stop_count=0,
        routing_count=1,
        duplicate_count=0,
        error_count=0,
        running=False,
        ready=True,
        last_validated_at=NOW,
        last_started_at=None,
        last_stopped_at=None,
        last_routed_at=NOW,
        last_error=None,
    )

    assert snapshot.instruments == (instrument_snapshot,)
    with pytest.raises(FrozenInstanceError):
        snapshot.routing_count = 2
    with pytest.raises(ValueError, match="routing_count"):
        TradeLifecycleInstrumentIntegrationSnapshot(
            instrument=Instrument.NIFTY,
            coordinator_snapshot=coordinator_snapshot,
            routing_count=-1,
            context_process_count=0,
            price_update_count=0,
            duplicate_count=0,
            blocked_count=0,
            rejected_count=0,
            error_count=0,
            last_routed_at=None,
            last_routing_result=None,
            last_error=None,
        )
