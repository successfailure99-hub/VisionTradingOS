"""
Immutable Position Management Engine V1 models.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isclose, isfinite
from numbers import Real

from application.execution_runtime_v1.models import ExecutionIntent, ExecutionResult
from core.enums.instrument import Instrument
from engines.market_context_v2.models import SUPPORTED_INSTRUMENTS
from engines.risk_management_v2.models import RiskManagementV2Snapshot
from engines.strategy_decision_v2.models import StrategyDecisionV2Snapshot
from engines.position_management_v1.enums import (
    PositionChange,
    PositionDecision,
    PositionExitReason,
    PositionPnlState,
    PositionSide,
    PositionStatus,
)


@dataclass(frozen=True, slots=True)
class PositionSource:
    execution_result: ExecutionResult
    execution_intent: ExecutionIntent
    risk_snapshot: RiskManagementV2Snapshot
    strategy_snapshot: StrategyDecisionV2Snapshot

    def __post_init__(self) -> None:
        if not isinstance(self.execution_result, ExecutionResult):
            raise TypeError("execution_result must be ExecutionResult")
        if not isinstance(self.execution_intent, ExecutionIntent):
            raise TypeError("execution_intent must be ExecutionIntent")
        if not isinstance(self.risk_snapshot, RiskManagementV2Snapshot):
            raise TypeError("risk_snapshot must be RiskManagementV2Snapshot")
        if not isinstance(self.strategy_snapshot, StrategyDecisionV2Snapshot):
            raise TypeError("strategy_snapshot must be StrategyDecisionV2Snapshot")
        if self.execution_result.intent != self.execution_intent:
            raise ValueError("execution result and intent must match")
        if self.execution_intent.risk_snapshot != self.risk_snapshot:
            raise ValueError("execution intent and risk snapshot must match")
        if self.risk_snapshot.strategy != self.strategy_snapshot:
            raise ValueError("risk and strategy snapshots must match")
        if self.execution_intent.instrument is not self.risk_snapshot.instrument or self.risk_snapshot.instrument is not self.strategy_snapshot.instrument:
            raise ValueError("source instruments must match")
        if self.execution_intent.created_at < self.strategy_snapshot.timestamp:
            raise ValueError("execution intent timestamp cannot precede strategy timestamp")
        if self.execution_intent.dry_run is not True or self.execution_intent.analysis_only is not True:
            raise ValueError("position source must be dry-run and analysis-only")


@dataclass(frozen=True, slots=True)
class ManagedPosition:
    position_id: str
    instrument: Instrument
    side: PositionSide
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    initial_quantity: int
    open_quantity: int
    closed_quantity: int
    average_entry_price: float
    current_price: float
    average_exit_price: float | None
    invalidation_price: float
    objective_price: float | None
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    pnl_state: PositionPnlState
    status: PositionStatus
    exit_reason: PositionExitReason
    source: PositionSource
    dry_run: bool
    analysis_only: bool

    def __post_init__(self) -> None:
        _non_empty(self.position_id, "position_id")
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        if not isinstance(self.side, PositionSide):
            raise TypeError("side must be PositionSide")
        _aware(self.opened_at, "opened_at")
        _aware(self.updated_at, "updated_at")
        if self.updated_at < self.opened_at:
            raise ValueError("updated_at cannot precede opened_at")
        if self.closed_at is not None:
            _aware(self.closed_at, "closed_at")
            if self.closed_at < self.opened_at:
                raise ValueError("closed_at cannot precede opened_at")
        _positive_int(self.initial_quantity, "initial_quantity")
        _non_negative_int(self.open_quantity, "open_quantity")
        _non_negative_int(self.closed_quantity, "closed_quantity")
        if self.open_quantity + self.closed_quantity != self.initial_quantity:
            raise ValueError("open and closed quantities must equal initial quantity")
        for name in ("average_entry_price", "current_price", "invalidation_price"):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        if self.average_exit_price is not None:
            object.__setattr__(self, "average_exit_price", _positive_real(self.average_exit_price, "average_exit_price"))
        if self.closed_quantity > 0 and self.average_exit_price is None:
            raise ValueError("exit price is required when quantity is closed")
        if self.objective_price is not None:
            object.__setattr__(self, "objective_price", _positive_real(self.objective_price, "objective_price"))
        if self.side is PositionSide.LONG:
            if self.invalidation_price >= self.average_entry_price:
                raise ValueError("LONG invalidation must be below entry")
            if self.objective_price is not None and self.objective_price <= self.average_entry_price:
                raise ValueError("LONG objective must be above entry")
        if self.side is PositionSide.SHORT:
            if self.invalidation_price <= self.average_entry_price:
                raise ValueError("SHORT invalidation must be above entry")
            if self.objective_price is not None and self.objective_price >= self.average_entry_price:
                raise ValueError("SHORT objective must be below entry")
        for name in ("realized_pnl", "unrealized_pnl", "total_pnl"):
            object.__setattr__(self, name, _finite_real(getattr(self, name), name))
        if not isclose(self.total_pnl, self.realized_pnl + self.unrealized_pnl, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("total P&L must equal realized plus unrealized P&L")
        if not isinstance(self.pnl_state, PositionPnlState):
            raise TypeError("pnl_state must be PositionPnlState")
        if not isinstance(self.status, PositionStatus):
            raise TypeError("status must be PositionStatus")
        if not isinstance(self.exit_reason, PositionExitReason):
            raise TypeError("exit_reason must be PositionExitReason")
        if not isinstance(self.source, PositionSource):
            raise TypeError("source must be PositionSource")
        if self.source.execution_intent.instrument is not self.instrument:
            raise ValueError("source instrument must match position")
        if self.status in {PositionStatus.CLOSED, PositionStatus.INVALIDATED} and self.open_quantity != 0:
            raise ValueError("closed positions must have zero open quantity")
        if self.status in {PositionStatus.OPEN, PositionStatus.PARTIALLY_CLOSED, PositionStatus.OBJECTIVE_REACHED} and self.open_quantity <= 0:
            raise ValueError("open positions must have open quantity")
        if self.dry_run is not True or self.analysis_only is not True:
            raise ValueError("managed positions must be dry-run and analysis-only")


@dataclass(frozen=True, slots=True)
class PositionPriceUpdate:
    instrument: Instrument
    timestamp: datetime
    market_price: float

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _aware(self.timestamp, "timestamp")
        object.__setattr__(self, "market_price", _positive_real(self.market_price, "market_price"))


@dataclass(frozen=True, slots=True)
class PositionExitRequest:
    timestamp: datetime
    quantity: int
    exit_price: float
    reason: PositionExitReason

    def __post_init__(self) -> None:
        _aware(self.timestamp, "timestamp")
        _positive_int(self.quantity, "quantity")
        object.__setattr__(self, "exit_price", _positive_real(self.exit_price, "exit_price"))
        if not isinstance(self.reason, PositionExitReason):
            raise TypeError("reason must be PositionExitReason")
        if self.reason is PositionExitReason.NONE:
            raise ValueError("exit reason cannot be NONE")


@dataclass(frozen=True, slots=True)
class PositionManagementResult:
    decision: PositionDecision
    position: ManagedPosition | None
    change: PositionChange
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PositionDecision):
            raise TypeError("decision must be PositionDecision")
        if self.position is not None and not isinstance(self.position, ManagedPosition):
            raise TypeError("position must be ManagedPosition or None")
        if self.decision is not PositionDecision.NO_POSITION and self.position is None:
            raise ValueError("position decision requires position")
        if not isinstance(self.change, PositionChange):
            raise TypeError("change must be PositionChange")
        _non_empty(self.message, "message")


@dataclass(frozen=True, slots=True)
class PositionManagementV1Snapshot:
    instrument: Instrument
    timestamp: datetime
    active_position: ManagedPosition | None
    last_result: PositionManagementResult | None
    opened_count: int
    partial_exit_count: int
    closed_count: int
    invalidation_exit_count: int
    objective_reached_count: int
    realized_pnl_total: float
    unrealized_pnl_total: float
    has_open_position: bool
    history_size: int
    last_error: str | None

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _aware(self.timestamp, "timestamp")
        if self.active_position is not None and not isinstance(self.active_position, ManagedPosition):
            raise TypeError("active_position must be ManagedPosition or None")
        if self.last_result is not None and not isinstance(self.last_result, PositionManagementResult):
            raise TypeError("last_result must be PositionManagementResult or None")
        for name in ("opened_count", "partial_exit_count", "closed_count", "invalidation_exit_count", "objective_reached_count", "history_size"):
            _non_negative_int(getattr(self, name), name)
        object.__setattr__(self, "realized_pnl_total", _finite_real(self.realized_pnl_total, "realized_pnl_total"))
        object.__setattr__(self, "unrealized_pnl_total", _finite_real(self.unrealized_pnl_total, "unrealized_pnl_total"))
        if type(self.has_open_position) is not bool:
            raise TypeError("has_open_position must be bool")
        if self.has_open_position != (self.active_position is not None):
            raise ValueError("has_open_position must match active position")
        if self.last_error is not None:
            _non_empty(self.last_error, "last_error")


def build_position_id(source: PositionSource) -> str:
    return f"{source.execution_intent.intent_id}:{source.execution_result.lifecycle[-1].timestamp.isoformat()}"


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _finite_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _positive_real(value: Real, name: str) -> float:
    number = _finite_real(value, name)
    if number <= 0.0:
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
