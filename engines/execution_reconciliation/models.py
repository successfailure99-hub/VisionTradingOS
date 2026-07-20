"""
Immutable Execution Reconciliation Engine V1 models.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from application.enums import RuntimeInstrument
from engines.order_management.enums import OrderSide, OrderStatus, OrderType
from engines.paper_execution_coordinator.models import PaperExecutionReceipt
from engines.position.enums import PositionStatus
from engines.position.models import PositionState
from engines.trade_execution_policy.models import TradeExecutionPlan
from engines.execution_reconciliation.enums import (
    ReconciliationBoundary,
    ReconciliationLifecycleState,
    ReconciliationReasonCode,
    ReconciliationSeverity,
    ReconciliationStatus,
)


SUPPORTED_INSTRUMENTS = ("BANKNIFTY", "NIFTY", "SENSEX")


@dataclass(frozen=True, slots=True)
class ExecutionReconciliationPolicy:
    enabled: bool = True
    allowed_instruments: tuple[str, ...] = SUPPORTED_INSTRUMENTS
    require_entry_order: bool = True
    require_managed_submission_for_every_order: bool = True
    require_stop_when_planned: bool = True
    require_target_when_planned: bool = True
    require_position_after_entry_fill: bool = True
    require_opposite_protection_cancel_after_exit: bool = True
    treat_missing_position_before_fill_as_valid: bool = True
    maximum_input_age_seconds: int | None = None
    maximum_findings: int = 100

    def __post_init__(self) -> None:
        for name in (
            "enabled",
            "require_entry_order",
            "require_managed_submission_for_every_order",
            "require_stop_when_planned",
            "require_target_when_planned",
            "require_position_after_entry_fill",
            "require_opposite_protection_cancel_after_exit",
            "treat_missing_position_before_fill_as_valid",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        instruments = tuple(_instrument(item) for item in self.allowed_instruments)
        if not instruments or len(set(instruments)) != len(instruments):
            raise ValueError("allowed_instruments must be unique and non-empty")
        object.__setattr__(self, "allowed_instruments", tuple(sorted(instruments)))
        if self.maximum_input_age_seconds is not None:
            _positive_int(self.maximum_input_age_seconds, "maximum_input_age_seconds")
        object.__setattr__(self, "maximum_findings", _positive_int(self.maximum_findings, "maximum_findings"))

    def fingerprint(self) -> str:
        return _fingerprint(_model_payload(self))


@dataclass(frozen=True, slots=True)
class ExecutionReconciliationRequest:
    request_id: str
    timestamp: datetime
    instrument: str | RuntimeInstrument
    execution_plan: TradeExecutionPlan
    execution_receipt: PaperExecutionReceipt
    entry_order: object | None = None
    stop_order: object | None = None
    target_order: object | None = None
    entry_managed_submission: object | None = None
    stop_managed_submission: object | None = None
    target_managed_submission: object | None = None
    position: PositionState | None = None
    existing_report_ids: tuple[str, ...] = ()
    correlation_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        _aware(self.timestamp, "timestamp")
        object.__setattr__(self, "instrument", _instrument(self.instrument))
        if not isinstance(self.execution_plan, TradeExecutionPlan):
            raise TypeError("execution_plan must be TradeExecutionPlan")
        if not isinstance(self.execution_receipt, PaperExecutionReceipt):
            raise TypeError("execution_receipt must be PaperExecutionReceipt")
        if self.position is not None and not isinstance(self.position, PositionState):
            raise TypeError("position must be PositionState or None")
        if not isinstance(self.existing_report_ids, tuple):
            raise TypeError("existing_report_ids must be tuple")
        object.__setattr__(self, "existing_report_ids", tuple(_text(item, "report_id") for item in self.existing_report_ids))
        object.__setattr__(self, "correlation_id", _optional_text(self.correlation_id))
        object.__setattr__(self, "session_id", _optional_text(self.session_id))

    def fingerprint(self) -> str:
        return _fingerprint(_model_payload(self))


@dataclass(frozen=True, slots=True)
class ReconciliationFinding:
    finding_id: str
    timestamp: datetime
    severity: ReconciliationSeverity
    reason_code: ReconciliationReasonCode
    message: str
    boundary: ReconciliationBoundary
    field_name: str | None = None
    observed_value: str | None = None
    expected_value: str | None = None
    related_identity: str | None = None
    occurrence_count: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", _text(self.finding_id, "finding_id"))
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.severity, ReconciliationSeverity):
            raise TypeError("severity must be ReconciliationSeverity")
        if not isinstance(self.reason_code, ReconciliationReasonCode):
            raise TypeError("reason_code must be ReconciliationReasonCode")
        if not isinstance(self.boundary, ReconciliationBoundary):
            raise TypeError("boundary must be ReconciliationBoundary")
        object.__setattr__(self, "message", _text(self.message, "message"))
        for name in ("field_name", "observed_value", "expected_value", "related_identity"):
            object.__setattr__(self, name, _optional_text(getattr(self, name)))
        object.__setattr__(self, "occurrence_count", _positive_int(self.occurrence_count, "occurrence_count"))


@dataclass(frozen=True, slots=True)
class ReconciledOrderState:
    purpose: str
    order_id: str | None
    managed_submission_id: str | None
    instrument: str | None
    side: OrderSide | None
    order_type: OrderType | None
    quantity: int | None
    filled_quantity: int | None
    remaining_quantity: int | None
    limit_price: float | None
    trigger_price: float | None
    order_status: OrderStatus | None
    managed_status: object | None
    reduce_only: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "purpose", _text(self.purpose, "purpose"))
        for name in ("order_id", "managed_submission_id", "instrument"):
            object.__setattr__(self, name, _optional_text(getattr(self, name)))
        if self.instrument is not None:
            object.__setattr__(self, "instrument", self.instrument.upper())
        for name in ("quantity", "filled_quantity", "remaining_quantity"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _non_negative_int(value, name))
        if type(self.reduce_only) is not bool:
            raise TypeError("reduce_only must be bool")


@dataclass(frozen=True, slots=True)
class ExecutionReconciliationReport:
    report_id: str
    created_at: datetime
    instrument: str
    execution_plan_id: str
    execution_plan_fingerprint: str
    receipt_id: str
    receipt_status: str
    reconciliation_status: ReconciliationStatus
    primary_reason: ReconciliationReasonCode
    findings: tuple[ReconciliationFinding, ...]
    entry: ReconciledOrderState | None
    stop: ReconciledOrderState | None
    target: ReconciledOrderState | None
    position_id: str | None
    position_status: PositionStatus | None
    position_quantity: int | None
    checked_boundaries: tuple[ReconciliationBoundary, ...]
    request_fingerprint: str
    input_fingerprint: str
    order_management_read_count: int
    paper_trading_read_count: int
    position_read_count: int
    broker_order_calls: int = 0
    mutation_calls: int = 0
    risk_decision_id: str | None = None
    signal_id: str | None = None
    strategy_id: str | None = None
    client_request_id: str | None = None
    correlation_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("report_id", "execution_plan_id", "execution_plan_fingerprint", "receipt_id", "receipt_status", "request_fingerprint", "input_fingerprint"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        _aware(self.created_at, "created_at")
        object.__setattr__(self, "instrument", _instrument(self.instrument))
        if not isinstance(self.reconciliation_status, ReconciliationStatus):
            raise TypeError("reconciliation_status must be ReconciliationStatus")
        if not isinstance(self.primary_reason, ReconciliationReasonCode):
            raise TypeError("primary_reason must be ReconciliationReasonCode")
        object.__setattr__(self, "findings", tuple(self.findings))
        if any(not isinstance(item, ReconciliationFinding) for item in self.findings):
            raise TypeError("findings must contain ReconciliationFinding values")
        for name in ("entry", "stop", "target"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, ReconciledOrderState):
                raise TypeError(f"{name} must be ReconciledOrderState or None")
        object.__setattr__(self, "position_id", _optional_text(self.position_id))
        if self.position_quantity is not None:
            object.__setattr__(self, "position_quantity", _non_negative_int(self.position_quantity, "position_quantity"))
        object.__setattr__(self, "checked_boundaries", tuple(self.checked_boundaries))
        if any(not isinstance(item, ReconciliationBoundary) for item in self.checked_boundaries):
            raise TypeError("checked_boundaries must contain ReconciliationBoundary values")
        for name in ("order_management_read_count", "paper_trading_read_count", "position_read_count", "broker_order_calls", "mutation_calls"):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))
        if self.broker_order_calls != 0 or self.mutation_calls != 0:
            raise ValueError("reconciliation must remain read-only")
        for name in ("risk_decision_id", "signal_id", "strategy_id", "client_request_id", "correlation_id", "session_id"):
            object.__setattr__(self, name, _optional_text(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class ExecutionReconciliationSnapshot:
    enabled: bool
    lifecycle_state: ReconciliationLifecycleState
    last_report: ExecutionReconciliationReport | None
    reconciliation_count: int
    consistent_count: int
    warning_count: int
    inconsistent_count: int
    incomplete_count: int
    invalid_count: int
    failed_count: int
    active_report_ids: tuple[str, ...]
    findings: tuple[ReconciliationFinding, ...]
    order_management_read_count: int
    paper_trading_read_count: int
    position_read_count: int
    broker_order_calls: int = 0
    mutation_calls: int = 0

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be bool")
        if not isinstance(self.lifecycle_state, ReconciliationLifecycleState):
            raise TypeError("lifecycle_state must be ReconciliationLifecycleState")
        if self.last_report is not None and not isinstance(self.last_report, ExecutionReconciliationReport):
            raise TypeError("last_report must be ExecutionReconciliationReport or None")
        for name in ("reconciliation_count", "consistent_count", "warning_count", "inconsistent_count", "incomplete_count", "invalid_count", "failed_count", "order_management_read_count", "paper_trading_read_count", "position_read_count", "broker_order_calls", "mutation_calls"):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))
        object.__setattr__(self, "active_report_ids", tuple(_text(item, "active_report_id") for item in self.active_report_ids))
        object.__setattr__(self, "findings", tuple(self.findings))
        if self.broker_order_calls != 0 or self.mutation_calls != 0:
            raise ValueError("reconciliation snapshot must remain read-only")


def report_identity(request: ExecutionReconciliationRequest, input_fingerprint: str) -> str:
    return _fingerprint({"request": request.fingerprint(), "input": input_fingerprint})


def finding_identity(timestamp: datetime, severity: ReconciliationSeverity, reason: ReconciliationReasonCode, boundary: ReconciliationBoundary, message: str, field_name=None, observed=None, expected=None, related=None) -> str:
    return _fingerprint(
        {
            "timestamp": timestamp.isoformat(),
            "severity": severity.value,
            "reason": reason.value,
            "boundary": boundary.value,
            "message": message,
            "field": field_name,
            "observed": observed,
            "expected": expected,
            "related": related,
        }
    )


def model_fingerprint(value) -> str:
    return _fingerprint(_model_payload(value))


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


def _text(value: str | None, name: str) -> str:
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


def _non_negative_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be non-negative integer")
    return value
