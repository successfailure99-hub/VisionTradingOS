"""
Immutable Trade Journal Runtime Integration V1 models.
"""

from dataclasses import dataclass
from datetime import datetime

from application.enums import ExecutionSafetyMode
from application.trade_journal_runtime_integration_v1.enums import (
    TradeJournalIntegrationChange,
    TradeJournalRoutingResult,
    TradeJournalRuntimeIntegrationStatus,
)
from application.trade_lifecycle_v1.models import TradeLifecycleV1Snapshot
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.market_context_v2.models import SUPPORTED_INSTRUMENTS
from engines.trade_journal_v1.models import (
    TradeJournalRecordResult,
    TradeJournalV1Snapshot,
    TradePerformanceAnalyticsSnapshot,
)
from engines.trade_journal_v1.enums import TradeRecordStatus


@dataclass(frozen=True, slots=True)
class TradeJournalRoutingRequest:
    instrument: Instrument
    lifecycle_snapshot: TradeLifecycleV1Snapshot

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        if not isinstance(self.lifecycle_snapshot, TradeLifecycleV1Snapshot):
            raise TypeError("lifecycle_snapshot must be TradeLifecycleV1Snapshot")
        if self.lifecycle_snapshot.instrument is not self.instrument:
            raise ValueError("routing instrument must match lifecycle snapshot")


@dataclass(frozen=True, slots=True)
class TradeJournalRoutingOutcome:
    instrument: Instrument
    result: TradeJournalRoutingResult
    lifecycle_snapshot: TradeLifecycleV1Snapshot
    journal_result: TradeJournalRecordResult | None
    routed_at: datetime
    message: str

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        if not isinstance(self.result, TradeJournalRoutingResult):
            raise TypeError("result must be TradeJournalRoutingResult")
        if not isinstance(self.lifecycle_snapshot, TradeLifecycleV1Snapshot):
            raise TypeError("lifecycle_snapshot must be TradeLifecycleV1Snapshot")
        if self.lifecycle_snapshot.instrument is not self.instrument:
            raise ValueError("lifecycle snapshot instrument mismatch")
        if self.journal_result is not None and not isinstance(self.journal_result, TradeJournalRecordResult):
            raise TypeError("journal_result must be TradeJournalRecordResult or None")
        if self.result is TradeJournalRoutingResult.RECORDED:
            if self.journal_result is None or self.journal_result.status is not TradeRecordStatus.RECORDED:
                raise ValueError("RECORDED routing requires recorded journal result")
        if self.result is TradeJournalRoutingResult.DUPLICATE:
            if self.journal_result is None or self.journal_result.status is not TradeRecordStatus.DUPLICATE:
                raise ValueError("DUPLICATE routing requires duplicate journal result")
        _aware(self.routed_at, "routed_at")
        _non_empty(self.message, "message")


@dataclass(frozen=True, slots=True)
class TradeJournalInstrumentRoutingSnapshot:
    instrument: Instrument
    routed_count: int
    recorded_count: int
    duplicate_count: int
    not_closed_count: int
    rejected_count: int
    error_count: int
    last_outcome: TradeJournalRoutingOutcome | None
    last_routed_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        for name in ("routed_count", "recorded_count", "duplicate_count", "not_closed_count", "rejected_count", "error_count"):
            _non_negative_int(getattr(self, name), name)
        if self.last_outcome is not None:
            if not isinstance(self.last_outcome, TradeJournalRoutingOutcome):
                raise TypeError("last_outcome must be TradeJournalRoutingOutcome or None")
            if self.last_outcome.instrument is not self.instrument:
                raise ValueError("last outcome instrument mismatch")
        if self.last_routed_at is not None:
            _aware(self.last_routed_at, "last_routed_at")
        if self.last_error is not None:
            _non_empty(self.last_error, "last_error")


@dataclass(frozen=True, slots=True)
class TradeJournalRuntimeIntegrationV1Snapshot:
    timestamp: datetime
    status: TradeJournalRuntimeIntegrationStatus
    change: TradeJournalIntegrationChange
    safety_mode: ExecutionSafetyMode
    broker_mode: BrokerExecutionMode
    journal_snapshot: TradeJournalV1Snapshot
    analytics_snapshot: TradePerformanceAnalyticsSnapshot
    instruments: tuple[TradeJournalInstrumentRoutingSnapshot, ...]
    routing_count: int
    recorded_count: int
    duplicate_count: int
    not_closed_count: int
    rejected_count: int
    error_count: int
    validation_count: int
    start_count: int
    stop_count: int
    running: bool
    ready: bool
    last_validated_at: datetime | None
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    last_routed_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.status, TradeJournalRuntimeIntegrationStatus):
            raise TypeError("status must be TradeJournalRuntimeIntegrationStatus")
        if not isinstance(self.change, TradeJournalIntegrationChange):
            raise TypeError("change must be TradeJournalIntegrationChange")
        if self.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
            raise ValueError("safety mode must be ANALYSIS_ONLY")
        if self.broker_mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("broker mode must be DRY_RUN")
        if not isinstance(self.journal_snapshot, TradeJournalV1Snapshot):
            raise TypeError("journal_snapshot must be TradeJournalV1Snapshot")
        if not isinstance(self.analytics_snapshot, TradePerformanceAnalyticsSnapshot):
            raise TypeError("analytics_snapshot must be TradePerformanceAnalyticsSnapshot")
        object.__setattr__(self, "instruments", _tuple_of(self.instruments, TradeJournalInstrumentRoutingSnapshot, "instruments"))
        for name in ("routing_count", "recorded_count", "duplicate_count", "not_closed_count", "rejected_count", "error_count", "validation_count", "start_count", "stop_count"):
            _non_negative_int(getattr(self, name), name)
        if type(self.running) is not bool or type(self.ready) is not bool:
            raise TypeError("running and ready must be bool")
        if self.running and self.status is not TradeJournalRuntimeIntegrationStatus.RUNNING:
            raise ValueError("running=True requires RUNNING status")
        for name in ("last_validated_at", "last_started_at", "last_stopped_at", "last_routed_at"):
            value = getattr(self, name)
            if value is not None:
                _aware(value, name)
        if self.last_error is not None:
            _non_empty(self.last_error, "last_error")


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be non-negative integer")


def _non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty string")


def _tuple_of(values, item_type, name: str):
    items = tuple(values)
    if any(not isinstance(item, item_type) for item in items):
        raise TypeError(f"{name} must contain {item_type.__name__}")
    return items
