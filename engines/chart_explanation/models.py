"""
Immutable Chart Explanation Engine V1 models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from application.enums import RuntimeInstrument

from .enums import ChartExplanationLifecycle, ExplanationQuality


@dataclass(frozen=True, slots=True)
class ChartExplanationSnapshot:
    trading_date: date
    instrument: RuntimeInstrument
    headline: str
    market_summary: str
    primary_setup_explanation: str
    supporting_evidence: tuple[str, ...]
    conflicting_evidence: tuple[str, ...]
    risk_notes: tuple[str, ...]
    explanation_quality: ExplanationQuality
    timestamp: datetime
    source_fingerprint: str
    trade_decision_generated: bool = False
    strategy_calls: int = 0
    confidence_calls: int = 0
    risk_calls: int = 0
    execution_calls: int = 0
    broker_order_calls: int = 0
    live_order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be a date.")
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        object.__setattr__(self, "headline", _normalize_text(self.headline, "headline"))
        object.__setattr__(self, "market_summary", _normalize_text(self.market_summary, "market_summary"))
        object.__setattr__(
            self,
            "primary_setup_explanation",
            _normalize_text(self.primary_setup_explanation, "primary_setup_explanation"),
        )
        object.__setattr__(self, "supporting_evidence", _normalize_text_tuple(self.supporting_evidence, "supporting_evidence"))
        object.__setattr__(self, "conflicting_evidence", _normalize_text_tuple(self.conflicting_evidence, "conflicting_evidence"))
        object.__setattr__(self, "risk_notes", _normalize_text_tuple(self.risk_notes, "risk_notes"))
        if not isinstance(self.explanation_quality, ExplanationQuality):
            raise TypeError("explanation_quality must be ExplanationQuality.")
        _validate_aware(self.timestamp, "timestamp")
        object.__setattr__(self, "source_fingerprint", _normalize_text(self.source_fingerprint, "source_fingerprint"))
        _validate_safety(self)


@dataclass(frozen=True, slots=True)
class ChartExplanationEngineSnapshot:
    enabled: bool
    lifecycle_state: ChartExplanationLifecycle
    explanation_count: int
    updated_count: int
    partial_count: int
    invalid_count: int
    failed_count: int
    last_snapshot: ChartExplanationSnapshot | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool.")
        if not isinstance(self.lifecycle_state, ChartExplanationLifecycle):
            raise TypeError("lifecycle_state must be ChartExplanationLifecycle.")
        for field_name in ("explanation_count", "updated_count", "partial_count", "invalid_count", "failed_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer.")
        if self.last_snapshot is not None and not isinstance(self.last_snapshot, ChartExplanationSnapshot):
            raise TypeError("last_snapshot must be ChartExplanationSnapshot or None.")
        if self.last_error is not None:
            object.__setattr__(self, "last_error", _normalize_text(self.last_error, "last_error"))


def _normalize_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple.")
    return tuple(_normalize_text(item, field_name) for item in values)


def _normalize_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text.")
    return value.strip()


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _validate_safety(snapshot: ChartExplanationSnapshot) -> None:
    if snapshot.trade_decision_generated is not False:
        raise ValueError("chart explanation must not generate trade decisions.")
    if snapshot.live_order_submission_enabled is not False:
        raise ValueError("chart explanation must keep live order submission disabled.")
    for field_name in (
        "strategy_calls",
        "confidence_calls",
        "risk_calls",
        "execution_calls",
        "broker_order_calls",
    ):
        value = getattr(snapshot, field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value != 0:
            raise ValueError(f"{field_name} must remain zero.")
