"""
Immutable Multi-Timeframe Evidence Fusion Engine V1 models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real

from application.enums import RuntimeInstrument

from .enums import (
    EvidenceAgreement,
    EvidenceCompleteness,
    EvidenceConflict,
    FusionDirection,
    FusionLifecycle,
)


@dataclass(frozen=True, slots=True)
class TimeframeEvidenceSummary:
    timeframe: str
    direction: FusionDirection
    completeness: EvidenceCompleteness
    missing_evidence: tuple[str, ...]
    invalid_evidence: tuple[str, ...]
    stale_evidence: tuple[str, ...]
    timestamp: datetime
    source_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "timeframe", _normalize_text(self.timeframe, "timeframe"))
        if not isinstance(self.direction, FusionDirection):
            raise TypeError("direction must be FusionDirection.")
        if not isinstance(self.completeness, EvidenceCompleteness):
            raise TypeError("completeness must be EvidenceCompleteness.")
        for field_name in ("missing_evidence", "invalid_evidence", "stale_evidence"):
            object.__setattr__(self, field_name, tuple(str(item).strip() for item in getattr(self, field_name)))
        _validate_aware(self.timestamp, "timestamp")
        object.__setattr__(self, "source_fingerprint", _normalize_text(self.source_fingerprint, "source_fingerprint"))


@dataclass(frozen=True, slots=True)
class MultiTimeframeEvidenceSnapshot:
    trading_date: date
    instrument: RuntimeInstrument
    timeframes: tuple[str, ...]
    evidence_agreement: EvidenceAgreement
    evidence_conflict: EvidenceConflict
    dominant_timeframe: str
    alignment_score: float
    conflict_score: float
    evidence_completeness: EvidenceCompleteness
    timestamp: datetime
    summaries: tuple[TimeframeEvidenceSummary, ...]
    available_timeframes: tuple[str, ...]
    missing_timeframes: tuple[str, ...]
    invalid_timeframes: tuple[str, ...]
    stale_timeframes: tuple[str, ...]
    aligned_timeframes: tuple[str, ...]
    conflicting_timeframes: tuple[str, ...]
    weak_timeframes: tuple[str, ...]
    source_fingerprint: str
    trade_decision_generated: bool = False
    strategy_calls: int = 0
    risk_calls: int = 0
    execution_policy_calls: int = 0
    authorization_calls: int = 0
    paper_execution_calls: int = 0
    broker_order_calls: int = 0
    live_order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be a date.")
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        object.__setattr__(self, "timeframes", tuple(_normalize_text(item, "timeframe") for item in self.timeframes))
        if not self.timeframes:
            raise ValueError("timeframes must not be empty.")
        if not isinstance(self.evidence_agreement, EvidenceAgreement):
            raise TypeError("evidence_agreement must be EvidenceAgreement.")
        if not isinstance(self.evidence_conflict, EvidenceConflict):
            raise TypeError("evidence_conflict must be EvidenceConflict.")
        object.__setattr__(self, "dominant_timeframe", _normalize_text(self.dominant_timeframe, "dominant_timeframe"))
        for field_name in ("alignment_score", "conflict_score"):
            _validate_percent(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, float(getattr(self, field_name)))
        if not isinstance(self.evidence_completeness, EvidenceCompleteness):
            raise TypeError("evidence_completeness must be EvidenceCompleteness.")
        _validate_aware(self.timestamp, "timestamp")
        object.__setattr__(self, "summaries", tuple(self.summaries))
        for summary in self.summaries:
            if not isinstance(summary, TimeframeEvidenceSummary):
                raise TypeError("summaries must contain TimeframeEvidenceSummary values.")
        for field_name in (
            "available_timeframes",
            "missing_timeframes",
            "invalid_timeframes",
            "stale_timeframes",
            "aligned_timeframes",
            "conflicting_timeframes",
            "weak_timeframes",
        ):
            object.__setattr__(self, field_name, tuple(_normalize_text(item, field_name) for item in getattr(self, field_name)))
        object.__setattr__(self, "source_fingerprint", _normalize_text(self.source_fingerprint, "source_fingerprint"))
        _validate_safety(self)


@dataclass(frozen=True, slots=True)
class MultiTimeframeEvidenceFusionSnapshot:
    enabled: bool
    lifecycle_state: FusionLifecycle
    fusion_count: int
    updated_count: int
    partial_count: int
    invalid_count: int
    failed_count: int
    last_snapshot: MultiTimeframeEvidenceSnapshot | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool.")
        if not isinstance(self.lifecycle_state, FusionLifecycle):
            raise TypeError("lifecycle_state must be FusionLifecycle.")
        for field_name in ("fusion_count", "updated_count", "partial_count", "invalid_count", "failed_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer.")
        if self.last_snapshot is not None and not isinstance(self.last_snapshot, MultiTimeframeEvidenceSnapshot):
            raise TypeError("last_snapshot must be MultiTimeframeEvidenceSnapshot or None.")
        if self.last_error is not None:
            object.__setattr__(self, "last_error", _normalize_text(self.last_error, "last_error"))


def _normalize_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text.")
    return value.strip()


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _validate_percent(value: Real, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)):
        raise TypeError(f"{field_name} must be a finite number.")
    if not 0 <= float(value) <= 100:
        raise ValueError(f"{field_name} must be between 0 and 100.")


def _validate_safety(snapshot: MultiTimeframeEvidenceSnapshot) -> None:
    if snapshot.trade_decision_generated is not False:
        raise ValueError("fusion snapshot must not generate trade decisions.")
    if snapshot.live_order_submission_enabled is not False:
        raise ValueError("fusion snapshot must keep live order submission disabled.")
    for field_name in (
        "strategy_calls",
        "risk_calls",
        "execution_policy_calls",
        "authorization_calls",
        "paper_execution_calls",
        "broker_order_calls",
    ):
        value = getattr(snapshot, field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value != 0:
            raise ValueError(f"{field_name} must remain zero.")
