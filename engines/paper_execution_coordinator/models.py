"""
Immutable Paper Execution Coordinator V1 models.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from numbers import Real

from application.enums import RuntimeInstrument
from engines.order_management.enums import OrderSide, OrderStatus, OrderType
from engines.trade_execution_policy.models import TradeExecutionPlan
from engines.paper_execution_coordinator.enums import (
    CoordinatedOrderPurpose,
    CoordinatorLifecycleState,
    PaperExecutionDecision,
    PaperExecutionReasonCode,
    PaperExecutionSeverity,
    PaperExecutionStatus,
)


SUPPORTED_INSTRUMENTS = ("BANKNIFTY", "NIFTY", "SENSEX")


@dataclass(frozen=True, slots=True)
class PaperExecutionCoordinatorPolicy:
    enabled: bool = True
    allowed_instruments: tuple[str, ...] = SUPPORTED_INSTRUMENTS
    require_ready_for_paper: bool = True
    require_plan_approval: bool = True
    require_paper_routing: bool = True
    require_plan_not_expired: bool = True
    one_receipt_per_execution_plan: bool = True
    create_stop_after_entry_fill: bool = True
    create_target_after_entry_fill: bool = True
    allow_partial_fill_protection: bool = False
    maximum_findings: int = 50

    def __post_init__(self) -> None:
        for name in (
            "enabled",
            "require_ready_for_paper",
            "require_plan_approval",
            "require_paper_routing",
            "require_plan_not_expired",
            "one_receipt_per_execution_plan",
            "create_stop_after_entry_fill",
            "create_target_after_entry_fill",
            "allow_partial_fill_protection",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        instruments = tuple(_instrument(item) for item in self.allowed_instruments)
        if not instruments or len(set(instruments)) != len(instruments):
            raise ValueError("allowed_instruments must be unique and non-empty")
        object.__setattr__(self, "allowed_instruments", tuple(sorted(instruments)))
        _positive_int(self.maximum_findings, "maximum_findings")

    def fingerprint(self) -> str:
        return _fingerprint(_model_payload(self))


@dataclass(frozen=True, slots=True)
class PaperExecutionRequest:
    request_id: str
    timestamp: datetime
    instrument: str | RuntimeInstrument
    execution_plan: TradeExecutionPlan
    existing_execution_receipt_ids: tuple[str, ...] = ()
    correlation_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        _aware(self.timestamp, "timestamp")
        object.__setattr__(self, "instrument", _instrument(self.instrument))
        if not isinstance(self.execution_plan, TradeExecutionPlan):
            raise TypeError("execution_plan must be TradeExecutionPlan")
        object.__setattr__(self, "existing_execution_receipt_ids", tuple(_text(item, "receipt_id") for item in self.existing_execution_receipt_ids))
        object.__setattr__(self, "correlation_id", _optional_text(self.correlation_id))
        object.__setattr__(self, "session_id", _optional_text(self.session_id))

    def fingerprint(self) -> str:
        return _fingerprint(_model_payload(self))


@dataclass(frozen=True, slots=True)
class PaperExecutionFinding:
    finding_id: str
    timestamp: datetime
    severity: PaperExecutionSeverity
    reason_code: PaperExecutionReasonCode
    message: str
    field_name: str | None = None
    observed_value: str | None = None
    expected_value: str | None = None
    occurrence_count: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", _text(self.finding_id, "finding_id"))
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.severity, PaperExecutionSeverity):
            raise TypeError("severity must be PaperExecutionSeverity")
        if not isinstance(self.reason_code, PaperExecutionReasonCode):
            raise TypeError("reason_code must be PaperExecutionReasonCode")
        object.__setattr__(self, "message", _text(self.message, "message"))
        object.__setattr__(self, "field_name", _optional_text(self.field_name))
        object.__setattr__(self, "observed_value", _optional_text(self.observed_value))
        object.__setattr__(self, "expected_value", _optional_text(self.expected_value))
        _positive_int(self.occurrence_count, "occurrence_count")


@dataclass(frozen=True, slots=True)
class CoordinatedOrderReference:
    order_id: str
    purpose: CoordinatedOrderPurpose
    side: OrderSide
    order_type: OrderType
    quantity: int
    limit_price: float | None
    trigger_price: float | None
    status: OrderStatus
    created_at: datetime
    reduce_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "order_id", _text(self.order_id, "order_id"))
        if not isinstance(self.purpose, CoordinatedOrderPurpose):
            raise TypeError("purpose must be CoordinatedOrderPurpose")
        if not isinstance(self.side, OrderSide):
            raise TypeError("side must be OrderSide")
        if not isinstance(self.order_type, OrderType):
            raise TypeError("order_type must be OrderType")
        object.__setattr__(self, "quantity", _positive_int(self.quantity, "quantity"))
        for name in ("limit_price", "trigger_price"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _positive_real(value, name))
        if not isinstance(self.status, OrderStatus):
            raise TypeError("status must be OrderStatus")
        _aware(self.created_at, "created_at")
        if type(self.reduce_only) is not bool:
            raise TypeError("reduce_only must be bool")


@dataclass(frozen=True, slots=True)
class PaperExecutionReceipt:
    receipt_id: str
    created_at: datetime
    updated_at: datetime
    instrument: str
    execution_plan_id: str
    execution_plan_fingerprint: str
    request_fingerprint: str
    entry_order: CoordinatedOrderReference | None
    stop_order: CoordinatedOrderReference | None
    target_order: CoordinatedOrderReference | None
    paper_submission_id: str | None
    status: PaperExecutionStatus
    decision: PaperExecutionDecision
    primary_reason: PaperExecutionReasonCode
    findings: tuple[PaperExecutionFinding, ...]
    entry_filled_quantity: int
    remaining_quantity: int
    broker_submission_allowed: bool
    broker_order_calls: int
    order_management_request_count: int
    paper_submission_count: int
    risk_decision_id: str | None = None
    signal_id: str | None = None
    strategy_id: str | None = None
    client_request_id: str | None = None
    correlation_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("receipt_id", "execution_plan_id", "execution_plan_fingerprint", "request_fingerprint"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        _aware(self.created_at, "created_at")
        _aware(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")
        object.__setattr__(self, "instrument", _instrument(self.instrument))
        for name in ("entry_order", "stop_order", "target_order"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, CoordinatedOrderReference):
                raise TypeError(f"{name} must be CoordinatedOrderReference or None")
        if self.paper_submission_id is not None:
            object.__setattr__(self, "paper_submission_id", _text(self.paper_submission_id, "paper_submission_id"))
        if not isinstance(self.status, PaperExecutionStatus):
            raise TypeError("status must be PaperExecutionStatus")
        if not isinstance(self.decision, PaperExecutionDecision):
            raise TypeError("decision must be PaperExecutionDecision")
        if not isinstance(self.primary_reason, PaperExecutionReasonCode):
            raise TypeError("primary_reason must be PaperExecutionReasonCode")
        object.__setattr__(self, "findings", tuple(self.findings))
        for name in ("entry_filled_quantity", "remaining_quantity", "order_management_request_count", "paper_submission_count", "broker_order_calls"):
            _non_negative_int(getattr(self, name), name)
        if self.broker_submission_allowed is not False or self.broker_order_calls != 0:
            raise ValueError("broker submission is not allowed")
        for name in ("risk_decision_id", "signal_id", "strategy_id", "client_request_id", "correlation_id", "session_id"):
            object.__setattr__(self, name, _optional_text(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class PaperExecutionCoordinatorSnapshot:
    enabled: bool
    lifecycle_state: CoordinatorLifecycleState
    last_receipt: PaperExecutionReceipt | None
    evaluation_count: int
    approved_count: int
    rejected_count: int
    duplicate_count: int
    expired_count: int
    failed_count: int
    active_receipt_ids: tuple[str, ...]
    findings: tuple[PaperExecutionFinding, ...]
    order_management_request_count: int
    paper_submission_count: int
    broker_order_calls: int = 0

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be bool")
        if not isinstance(self.lifecycle_state, CoordinatorLifecycleState):
            raise TypeError("lifecycle_state must be CoordinatorLifecycleState")
        if self.last_receipt is not None and not isinstance(self.last_receipt, PaperExecutionReceipt):
            raise TypeError("last_receipt must be PaperExecutionReceipt or None")
        for name in ("evaluation_count", "approved_count", "rejected_count", "duplicate_count", "expired_count", "failed_count", "order_management_request_count", "paper_submission_count", "broker_order_calls"):
            _non_negative_int(getattr(self, name), name)
        object.__setattr__(self, "active_receipt_ids", tuple(_text(item, "active_receipt_id") for item in self.active_receipt_ids))
        object.__setattr__(self, "findings", tuple(self.findings))
        if self.broker_order_calls != 0:
            raise ValueError("broker_order_calls must remain zero")


def receipt_identity(request: PaperExecutionRequest, policy: PaperExecutionCoordinatorPolicy) -> str:
    return _fingerprint(
        {
            "request": request.fingerprint(),
            "plan": request.execution_plan.execution_plan_id,
            "plan_fingerprint": request.execution_plan.input_fingerprint,
            "policy": policy.fingerprint(),
        }
    )


def finding_identity(timestamp: datetime, reason: PaperExecutionReasonCode, message: str, field_name=None, observed=None, expected=None) -> str:
    return _fingerprint(
        {
            "timestamp": timestamp.isoformat(),
            "reason": reason.value,
            "message": message,
            "field": field_name,
            "observed": observed,
            "expected": expected,
        }
    )


def _model_payload(value):
    if hasattr(value, "__dataclass_fields__"):
        return {key: _model_payload(getattr(value, key)) for key in sorted(value.__dataclass_fields__)}
    if isinstance(value, dict):
        return {str(key): _model_payload(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_model_payload(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _fingerprint(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _instrument(value: str | RuntimeInstrument) -> str:
    raw = value.value if isinstance(value, RuntimeInstrument) else value
    if not isinstance(raw, str):
        raise TypeError("instrument must be text")
    normalized = raw.strip().upper()
    if normalized not in SUPPORTED_INSTRUMENTS:
        raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
    return normalized


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()[:500]


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _text(value, "text")


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive integer")
    return value


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be non-negative integer")


def _positive_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be positive")
    return number
