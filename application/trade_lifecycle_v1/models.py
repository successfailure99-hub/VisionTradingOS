"""
Immutable Trade Lifecycle Coordinator V1 models.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from numbers import Real

from application.execution_runtime_v1.models import ExecutionResult, ExecutionRuntimeV1Snapshot
from application.trade_lifecycle_v1.enums import (
    TradeLifecycleBlockSource,
    TradeLifecycleChange,
    TradeLifecycleOutcome,
    TradeLifecycleStage,
    TradeLifecycleStatus,
)
from core.enums.instrument import Instrument
from engines.position_management_v1.models import PositionManagementResult, PositionManagementV1Snapshot
from engines.risk_management_v2.models import SUPPORTED_INSTRUMENTS, RiskManagementV2Snapshot
from engines.strategy_decision_v2.models import StrategyDecisionV2Snapshot


@dataclass(frozen=True, slots=True)
class TradeLifecycleV1Request:
    strategy_decision: StrategyDecisionV2Snapshot
    risk_decision: RiskManagementV2Snapshot

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_decision, StrategyDecisionV2Snapshot):
            raise TypeError("strategy_decision must be StrategyDecisionV2Snapshot")
        if not isinstance(self.risk_decision, RiskManagementV2Snapshot):
            raise TypeError("risk_decision must be RiskManagementV2Snapshot")
        if self.strategy_decision.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        if self.risk_decision.strategy is not self.strategy_decision:
            raise ValueError("risk decision must reference the supplied strategy decision")
        if self.risk_decision.instrument is not self.strategy_decision.instrument:
            raise ValueError("risk decision instrument must match strategy decision")
        if self.risk_decision.timestamp != self.strategy_decision.timestamp:
            raise ValueError("risk decision timestamp must match strategy decision")

    @property
    def instrument(self) -> Instrument:
        return self.strategy_decision.instrument


@dataclass(frozen=True, slots=True)
class TradeLifecycleStageRecord:
    sequence: int
    timestamp: datetime
    stage: TradeLifecycleStage
    outcome: TradeLifecycleOutcome
    message: str

    def __post_init__(self) -> None:
        _positive_int(self.sequence, "sequence")
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.stage, TradeLifecycleStage):
            raise TypeError("stage must be TradeLifecycleStage")
        if not isinstance(self.outcome, TradeLifecycleOutcome):
            raise TypeError("outcome must be TradeLifecycleOutcome")
        _non_empty(self.message, "message")


@dataclass(frozen=True, slots=True)
class TradeLifecycleV1Snapshot:
    instrument: Instrument
    timestamp: datetime
    lifecycle_status: TradeLifecycleStatus
    stage: TradeLifecycleStage
    outcome: TradeLifecycleOutcome
    change: TradeLifecycleChange
    block_source: TradeLifecycleBlockSource
    strategy_decision: StrategyDecisionV2Snapshot | None
    risk_decision: RiskManagementV2Snapshot | None
    execution_result: ExecutionResult | None
    position_result: PositionManagementResult | None
    execution_snapshot: ExecutionRuntimeV1Snapshot
    position_snapshot: PositionManagementV1Snapshot
    stage_records: tuple[TradeLifecycleStageRecord, ...]
    processing_count: int
    waiting_count: int
    blocked_count: int
    rejected_count: int
    execution_count: int
    position_open_count: int
    position_close_count: int
    running: bool
    ready: bool
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    last_processed_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _aware(self.timestamp, "timestamp")
        for name, enum_type in (
            ("lifecycle_status", TradeLifecycleStatus),
            ("stage", TradeLifecycleStage),
            ("outcome", TradeLifecycleOutcome),
            ("change", TradeLifecycleChange),
            ("block_source", TradeLifecycleBlockSource),
        ):
            if not isinstance(getattr(self, name), enum_type):
                raise TypeError(f"{name} must be {enum_type.__name__}")
        for name in ("strategy_decision", "risk_decision"):
            value = getattr(self, name)
            if value is not None and value.instrument is not self.instrument:
                raise ValueError(f"{name} instrument mismatch")
        if self.risk_decision is not None and self.strategy_decision is not None:
            if self.risk_decision.strategy is not self.strategy_decision:
                raise ValueError("risk decision must reference strategy decision")
        if self.execution_result is not None and not isinstance(self.execution_result, ExecutionResult):
            raise TypeError("execution_result must be ExecutionResult or None")
        if self.position_result is not None and not isinstance(self.position_result, PositionManagementResult):
            raise TypeError("position_result must be PositionManagementResult or None")
        if not isinstance(self.execution_snapshot, ExecutionRuntimeV1Snapshot):
            raise TypeError("execution_snapshot must be ExecutionRuntimeV1Snapshot")
        if not isinstance(self.position_snapshot, PositionManagementV1Snapshot):
            raise TypeError("position_snapshot must be PositionManagementV1Snapshot")
        object.__setattr__(self, "stage_records", _tuple_of(self.stage_records, TradeLifecycleStageRecord, "stage_records"))
        for name in ("processing_count", "waiting_count", "blocked_count", "rejected_count", "execution_count", "position_open_count", "position_close_count"):
            _non_negative_int(getattr(self, name), name)
        if type(self.running) is not bool or type(self.ready) is not bool:
            raise TypeError("running and ready must be bool")
        if self.running and self.lifecycle_status is not TradeLifecycleStatus.RUNNING:
            raise ValueError("running=True requires RUNNING lifecycle status")
        for name in ("last_started_at", "last_stopped_at", "last_processed_at"):
            value = getattr(self, name)
            if value is not None:
                _aware(value, name)
        if self.last_error is not None:
            _non_empty(self.last_error, "last_error")


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _positive_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be positive")
    return number


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive integer")


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
