"""
Immutable Execution Runtime V1 models.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from numbers import Real

from core.enums.instrument import Instrument
from engines.risk_management_v2.enums import RiskDecision
from engines.risk_management_v2.models import SUPPORTED_INSTRUMENTS, RiskManagementV2Snapshot
from engines.strategy_decision_v2.enums import StrategyDirection
from application.execution_runtime_v1.enums import (
    ExecutionDecision,
    ExecutionIntentStatus,
    ExecutionOrderType,
    ExecutionRuntimeStatus,
    ExecutionSide,
)


@dataclass(frozen=True, slots=True)
class ExecutionIntent:
    intent_id: str
    instrument: Instrument
    created_at: datetime
    side: ExecutionSide
    quantity: int
    order_type: ExecutionOrderType
    limit_price: float | None
    reference_entry_price: float
    invalidation_price: float
    objective_price: float | None
    risk_snapshot: RiskManagementV2Snapshot
    status: ExecutionIntentStatus
    dry_run: bool
    analysis_only: bool

    def __post_init__(self) -> None:
        _non_empty(self.intent_id, "intent_id")
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _aware(self.created_at, "created_at")
        if not isinstance(self.side, ExecutionSide):
            raise TypeError("side must be ExecutionSide")
        _positive_int(self.quantity, "quantity")
        if not isinstance(self.order_type, ExecutionOrderType):
            raise TypeError("order_type must be ExecutionOrderType")
        if self.limit_price is not None:
            object.__setattr__(self, "limit_price", _positive_real(self.limit_price, "limit_price"))
        if self.order_type is ExecutionOrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit price is required for LIMIT orders")
        for name in ("reference_entry_price", "invalidation_price"):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        if self.objective_price is not None:
            object.__setattr__(self, "objective_price", _positive_real(self.objective_price, "objective_price"))
        if not isinstance(self.risk_snapshot, RiskManagementV2Snapshot):
            raise TypeError("risk_snapshot must be RiskManagementV2Snapshot")
        if self.risk_snapshot.instrument is not self.instrument:
            raise ValueError("risk snapshot instrument mismatch")
        if not self.risk_snapshot.execution_eligible:
            raise ValueError("risk snapshot must be execution eligible")
        if self.quantity != self.risk_snapshot.approved_quantity:
            raise ValueError("execution quantity must equal approved risk quantity")
        if self.risk_snapshot.strategy.direction is StrategyDirection.LONG and self.side is not ExecutionSide.BUY:
            raise ValueError("LONG strategy maps to BUY")
        if self.risk_snapshot.strategy.direction is StrategyDirection.SHORT and self.side is not ExecutionSide.SELL:
            raise ValueError("SHORT strategy maps to SELL")
        if not isinstance(self.status, ExecutionIntentStatus):
            raise TypeError("status must be ExecutionIntentStatus")
        if self.dry_run is not True or self.analysis_only is not True:
            raise ValueError("Execution Runtime V1 intents must be dry-run and analysis-only")


@dataclass(frozen=True, slots=True)
class ExecutionLifecycleEvent:
    sequence: int
    timestamp: datetime
    status: ExecutionIntentStatus
    message: str
    filled_quantity: int
    remaining_quantity: int
    simulated_fill_price: float | None

    def __post_init__(self) -> None:
        _positive_int(self.sequence, "sequence")
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.status, ExecutionIntentStatus):
            raise TypeError("status must be ExecutionIntentStatus")
        _non_empty(self.message, "message")
        _non_negative_int(self.filled_quantity, "filled_quantity")
        _non_negative_int(self.remaining_quantity, "remaining_quantity")
        if self.filled_quantity > 0:
            object.__setattr__(self, "simulated_fill_price", _positive_real(self.simulated_fill_price, "simulated_fill_price"))
        elif self.simulated_fill_price is not None:
            object.__setattr__(self, "simulated_fill_price", _positive_real(self.simulated_fill_price, "simulated_fill_price"))


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    decision: ExecutionDecision
    intent: ExecutionIntent | None
    lifecycle: tuple[ExecutionLifecycleEvent, ...]
    accepted_quantity: int
    filled_quantity: int
    remaining_quantity: int
    average_fill_price: float | None
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ExecutionDecision):
            raise TypeError("decision must be ExecutionDecision")
        if self.intent is not None and not isinstance(self.intent, ExecutionIntent):
            raise TypeError("intent must be ExecutionIntent or None")
        if self.decision is ExecutionDecision.ACCEPTED and self.intent is None:
            raise ValueError("accepted execution requires intent")
        object.__setattr__(self, "lifecycle", _tuple_of(self.lifecycle, ExecutionLifecycleEvent, "lifecycle"))
        for name in ("accepted_quantity", "filled_quantity", "remaining_quantity"):
            _non_negative_int(getattr(self, name), name)
        if self.filled_quantity > self.accepted_quantity:
            raise ValueError("filled quantity cannot exceed accepted quantity")
        if self.filled_quantity > 0:
            object.__setattr__(self, "average_fill_price", _positive_real(self.average_fill_price, "average_fill_price"))
        _non_empty(self.message, "message")


@dataclass(frozen=True, slots=True)
class ExecutionRuntimeV1Snapshot:
    instrument: Instrument
    timestamp: datetime
    runtime_status: ExecutionRuntimeStatus
    execution_decision: ExecutionDecision
    active_intent: ExecutionIntent | None
    last_result: ExecutionResult | None
    submitted_count: int
    acknowledged_count: int
    partial_fill_count: int
    fill_count: int
    cancel_count: int
    reject_count: int
    open_intent_count: int
    running: bool
    ready: bool
    history_size: int
    last_error: str | None

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.runtime_status, ExecutionRuntimeStatus):
            raise TypeError("runtime_status must be ExecutionRuntimeStatus")
        if not isinstance(self.execution_decision, ExecutionDecision):
            raise TypeError("execution_decision must be ExecutionDecision")
        if self.active_intent is not None and not isinstance(self.active_intent, ExecutionIntent):
            raise TypeError("active_intent must be ExecutionIntent or None")
        if self.last_result is not None and not isinstance(self.last_result, ExecutionResult):
            raise TypeError("last_result must be ExecutionResult or None")
        for name in (
            "submitted_count",
            "acknowledged_count",
            "partial_fill_count",
            "fill_count",
            "cancel_count",
            "reject_count",
            "open_intent_count",
            "history_size",
        ):
            _non_negative_int(getattr(self, name), name)
        if type(self.running) is not bool or type(self.ready) is not bool:
            raise TypeError("running and ready must be bool")
        if self.running and self.runtime_status is not ExecutionRuntimeStatus.RUNNING:
            raise ValueError("running=True requires RUNNING status")
        if self.last_error is not None:
            _non_empty(self.last_error, "last_error")


def build_intent_id(risk: RiskManagementV2Snapshot) -> str:
    direction = risk.strategy.direction.value
    stamp = risk.timestamp.isoformat()
    return f"{risk.instrument.value}:{stamp}:{direction}:{risk.approved_quantity}"


def side_from_risk(risk: RiskManagementV2Snapshot) -> ExecutionSide:
    if risk.strategy.direction is StrategyDirection.LONG:
        return ExecutionSide.BUY
    if risk.strategy.direction is StrategyDirection.SHORT:
        return ExecutionSide.SELL
    return ExecutionSide.NONE


def intent_from_risk(
    risk: RiskManagementV2Snapshot,
    *,
    created_at: datetime,
    order_type: ExecutionOrderType,
) -> ExecutionIntent:
    return ExecutionIntent(
        intent_id=build_intent_id(risk),
        instrument=risk.instrument,
        created_at=created_at,
        side=side_from_risk(risk),
        quantity=risk.approved_quantity,
        order_type=order_type,
        limit_price=risk.entry_price if order_type is ExecutionOrderType.LIMIT else None,
        reference_entry_price=risk.entry_price,
        invalidation_price=risk.invalidation_price,
        objective_price=risk.objective_price,
        risk_snapshot=risk,
        status=ExecutionIntentStatus.CREATED,
        dry_run=True,
        analysis_only=True,
    )


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
