"""
Immutable Shadow Trading Session Engine V1 models.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from application.enums import RuntimeInstrument

from .enums import ShadowSessionLifecycleState, ShadowSessionStatus


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


def _text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} cannot be empty")
    return normalized


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _text(value, "optional text")


def _instrument(value: str) -> str:
    normalized = _text(value, "instrument").upper()
    if normalized not in {item.value for item in RuntimeInstrument}:
        raise ValueError("unsupported instrument")
    return normalized


def _non_negative_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _metadata(value) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, tuple):
        raise TypeError("metadata must be a tuple")
    normalized = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("metadata entries must be key/value tuples")
        normalized.append((_text(item[0], "metadata key"), _text(item[1], "metadata value")))
    return tuple(sorted(normalized))


def fingerprint_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ShadowTradingSessionRequest:
    session_id: str
    started_at: datetime
    instrument: str
    correlation_id: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _text(self.session_id, "session_id"))
        object.__setattr__(self, "started_at", _aware(self.started_at, "started_at"))
        object.__setattr__(self, "instrument", _instrument(self.instrument))
        object.__setattr__(self, "correlation_id", _optional_text(self.correlation_id))
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def fingerprint(self) -> str:
        return fingerprint_payload(
            {
                "session_id": self.session_id,
                "started_at": self.started_at.isoformat(),
                "instrument": self.instrument,
                "correlation_id": self.correlation_id,
                "metadata": self.metadata,
            }
        )


@dataclass(frozen=True, slots=True)
class ShadowSessionObservation:
    observation_id: str
    timestamp: datetime
    instrument: str
    event_name: str
    execution_plan_id: str | None
    execution_receipt_id: str | None
    reconciliation_report_id: str | None
    position_id: str | None
    status: str
    reason: str
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _text(self.observation_id, "observation_id"))
        object.__setattr__(self, "timestamp", _aware(self.timestamp, "timestamp"))
        object.__setattr__(self, "instrument", _instrument(self.instrument))
        object.__setattr__(self, "event_name", _text(self.event_name, "event_name"))
        for name in ("execution_plan_id", "execution_receipt_id", "reconciliation_report_id", "position_id", "correlation_id"):
            object.__setattr__(self, name, _optional_text(getattr(self, name)))
        object.__setattr__(self, "status", _text(self.status, "status"))
        object.__setattr__(self, "reason", _text(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class ShadowTradingSessionSummary:
    session_id: str
    started_at: datetime
    ended_at: datetime
    instrument: str
    lifecycle_state: ShadowSessionLifecycleState
    session_status: ShadowSessionStatus
    primary_reason: str
    market_event_count: int
    execution_plan_count: int
    approved_plan_count: int
    rejected_plan_count: int
    paper_receipt_count: int
    paper_completed_count: int
    paper_cancelled_count: int
    paper_failed_count: int
    reconciliation_report_count: int
    consistent_reconciliation_count: int
    warning_reconciliation_count: int
    incomplete_reconciliation_count: int
    inconsistent_reconciliation_count: int
    invalid_reconciliation_count: int
    failed_reconciliation_count: int
    position_open_count: int
    position_closed_count: int
    observations: tuple[ShadowSessionObservation, ...]
    latest_execution_plan_id: str | None
    latest_execution_receipt_id: str | None
    latest_reconciliation_report_id: str | None
    latest_position_id: str | None
    broker_order_calls: int = 0
    mutation_calls: int = 0
    live_order_submission_enabled: bool = False
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _text(self.session_id, "session_id"))
        object.__setattr__(self, "started_at", _aware(self.started_at, "started_at"))
        object.__setattr__(self, "ended_at", _aware(self.ended_at, "ended_at"))
        object.__setattr__(self, "instrument", _instrument(self.instrument))
        if self.ended_at < self.started_at:
            raise ValueError("ended_at cannot be before started_at")
        if not isinstance(self.lifecycle_state, ShadowSessionLifecycleState):
            raise TypeError("lifecycle_state must be ShadowSessionLifecycleState")
        if not isinstance(self.session_status, ShadowSessionStatus):
            raise TypeError("session_status must be ShadowSessionStatus")
        object.__setattr__(self, "primary_reason", _text(self.primary_reason, "primary_reason"))
        for name in (
            "market_event_count",
            "execution_plan_count",
            "approved_plan_count",
            "rejected_plan_count",
            "paper_receipt_count",
            "paper_completed_count",
            "paper_cancelled_count",
            "paper_failed_count",
            "reconciliation_report_count",
            "consistent_reconciliation_count",
            "warning_reconciliation_count",
            "incomplete_reconciliation_count",
            "inconsistent_reconciliation_count",
            "invalid_reconciliation_count",
            "failed_reconciliation_count",
            "position_open_count",
            "position_closed_count",
        ):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))
        object.__setattr__(self, "observations", tuple(self.observations))
        if any(not isinstance(item, ShadowSessionObservation) for item in self.observations):
            raise TypeError("observations must contain ShadowSessionObservation values")
        for name in ("latest_execution_plan_id", "latest_execution_receipt_id", "latest_reconciliation_report_id", "latest_position_id", "correlation_id"):
            object.__setattr__(self, name, _optional_text(getattr(self, name)))
        if self.broker_order_calls != 0 or self.mutation_calls != 0 or self.live_order_submission_enabled is not False:
            raise ValueError("shadow session must remain read-only")

    def fingerprint(self) -> str:
        return fingerprint_payload(
            {
                "session_id": self.session_id,
                "ended_at": self.ended_at.isoformat(),
                "instrument": self.instrument,
                "status": self.session_status.value,
                "observations": tuple(item.observation_id for item in self.observations),
            }
        )


@dataclass(frozen=True, slots=True)
class ShadowTradingSessionSnapshot:
    enabled: bool
    lifecycle_state: ShadowSessionLifecycleState
    active_session_id: str | None
    last_summary: ShadowTradingSessionSummary | None
    session_count: int
    completed_session_count: int
    failed_session_count: int
    market_event_count: int
    execution_plan_count: int
    paper_receipt_count: int
    reconciliation_report_count: int
    open_position_count: int
    closed_position_count: int
    broker_order_calls: int = 0
    mutation_calls: int = 0
    live_order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be bool")
        if not isinstance(self.lifecycle_state, ShadowSessionLifecycleState):
            raise TypeError("lifecycle_state must be ShadowSessionLifecycleState")
        object.__setattr__(self, "active_session_id", _optional_text(self.active_session_id))
        if self.last_summary is not None and not isinstance(self.last_summary, ShadowTradingSessionSummary):
            raise TypeError("last_summary must be ShadowTradingSessionSummary or None")
        for name in (
            "session_count",
            "completed_session_count",
            "failed_session_count",
            "market_event_count",
            "execution_plan_count",
            "paper_receipt_count",
            "reconciliation_report_count",
            "open_position_count",
            "closed_position_count",
        ):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))
        if self.broker_order_calls != 0 or self.mutation_calls != 0 or self.live_order_submission_enabled is not False:
            raise ValueError("shadow snapshot must remain read-only")
