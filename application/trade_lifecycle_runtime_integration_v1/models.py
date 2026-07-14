"""
Immutable Trade Lifecycle Runtime Integration V1 models.
"""

from dataclasses import dataclass
from datetime import datetime

from application.enums import ExecutionSafetyMode, RuntimeStatus
from application.trade_lifecycle_runtime_integration_v1.enums import (
    TradeLifecycleIntegrationChange,
    TradeLifecycleRoutingResult,
    TradeLifecycleRuntimeIntegrationStatus,
)
from application.trade_lifecycle_v1.models import TradeLifecycleV1Request, TradeLifecycleV1Snapshot
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.market_context_v2.models import SUPPORTED_INSTRUMENTS
from engines.position_management_v1.models import PositionPriceUpdate


@dataclass(frozen=True, slots=True)
class TradeLifecycleRoutingRequest:
    instrument: Instrument
    lifecycle_request: TradeLifecycleV1Request

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        if not isinstance(self.lifecycle_request, TradeLifecycleV1Request):
            raise TypeError("lifecycle_request must be TradeLifecycleV1Request")
        if self.lifecycle_request.market_context.instrument is not self.instrument:
            raise ValueError("routing instrument must match lifecycle request")


@dataclass(frozen=True, slots=True)
class TradeLifecyclePositionPriceRequest:
    instrument: Instrument
    update: PositionPriceUpdate

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        if not isinstance(self.update, PositionPriceUpdate):
            raise TypeError("update must be PositionPriceUpdate")
        if self.update.instrument is not self.instrument:
            raise ValueError("price update instrument mismatch")


@dataclass(frozen=True, slots=True)
class TradeLifecycleInstrumentIntegrationSnapshot:
    instrument: Instrument
    coordinator_snapshot: TradeLifecycleV1Snapshot
    routing_count: int
    context_process_count: int
    price_update_count: int
    duplicate_count: int
    blocked_count: int
    rejected_count: int
    error_count: int
    last_routed_at: datetime | None
    last_routing_result: TradeLifecycleRoutingResult | None
    last_error: str | None

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        if not isinstance(self.coordinator_snapshot, TradeLifecycleV1Snapshot):
            raise TypeError("coordinator_snapshot must be TradeLifecycleV1Snapshot")
        if self.coordinator_snapshot.instrument is not self.instrument:
            raise ValueError("coordinator snapshot instrument mismatch")
        for name in ("routing_count", "context_process_count", "price_update_count", "duplicate_count", "blocked_count", "rejected_count", "error_count"):
            _non_negative_int(getattr(self, name), name)
        if self.last_routed_at is not None:
            _aware(self.last_routed_at, "last_routed_at")
        if self.last_routing_result is not None and not isinstance(self.last_routing_result, TradeLifecycleRoutingResult):
            raise TypeError("last_routing_result must be TradeLifecycleRoutingResult or None")
        if self.last_error is not None and not self.last_error.strip():
            raise ValueError("last_error must be non-empty")


@dataclass(frozen=True, slots=True)
class TradeLifecycleRuntimeIntegrationV1Snapshot:
    timestamp: datetime
    status: TradeLifecycleRuntimeIntegrationStatus
    change: TradeLifecycleIntegrationChange
    application_status: RuntimeStatus | None
    safety_mode: ExecutionSafetyMode
    broker_mode: BrokerExecutionMode
    instruments: tuple[TradeLifecycleInstrumentIntegrationSnapshot, ...]
    configured_instrument_count: int
    ready_instrument_count: int
    running_instrument_count: int
    active_execution_count: int
    active_position_count: int
    validation_count: int
    start_count: int
    stop_count: int
    routing_count: int
    duplicate_count: int
    error_count: int
    running: bool
    ready: bool
    last_validated_at: datetime | None
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    last_routed_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.status, TradeLifecycleRuntimeIntegrationStatus):
            raise TypeError("status must be TradeLifecycleRuntimeIntegrationStatus")
        if not isinstance(self.change, TradeLifecycleIntegrationChange):
            raise TypeError("change must be TradeLifecycleIntegrationChange")
        if self.application_status is not None and not isinstance(self.application_status, RuntimeStatus):
            raise TypeError("application_status must be RuntimeStatus or None")
        if self.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
            raise ValueError("safety mode must be ANALYSIS_ONLY")
        if self.broker_mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("broker mode must be DRY_RUN")
        object.__setattr__(self, "instruments", _tuple_of(self.instruments, TradeLifecycleInstrumentIntegrationSnapshot, "instruments"))
        for name in (
            "configured_instrument_count",
            "ready_instrument_count",
            "running_instrument_count",
            "active_execution_count",
            "active_position_count",
            "validation_count",
            "start_count",
            "stop_count",
            "routing_count",
            "duplicate_count",
            "error_count",
        ):
            _non_negative_int(getattr(self, name), name)
        if type(self.running) is not bool or type(self.ready) is not bool:
            raise TypeError("running and ready must be bool")
        if self.running and self.status is not TradeLifecycleRuntimeIntegrationStatus.RUNNING:
            raise ValueError("running=True requires RUNNING status")
        for name in ("last_validated_at", "last_started_at", "last_stopped_at", "last_routed_at"):
            value = getattr(self, name)
            if value is not None:
                _aware(value, name)
        if self.last_error is not None and not self.last_error.strip():
            raise ValueError("last_error must be non-empty")


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be non-negative integer")


def _tuple_of(values, item_type, name: str):
    items = tuple(values)
    if any(not isinstance(item, item_type) for item in items):
        raise TypeError(f"{name} must contain {item_type.__name__}")
    return items
