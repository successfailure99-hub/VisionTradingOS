"""
Immutable Expert Setup Classification Engine V1 models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from application.enums import RuntimeInstrument

from .enums import (
    ExpertSetup,
    SetupClassificationLifecycle,
    SetupQuality,
    SetupStability,
    SetupStrength,
)


@dataclass(frozen=True, slots=True)
class ExpertSetupClassificationSnapshot:
    trading_date: date
    instrument: RuntimeInstrument
    primary_setup: ExpertSetup
    secondary_setup: ExpertSetup
    setup_strength: SetupStrength
    setup_quality: SetupQuality
    setup_stability: SetupStability
    supporting_evidence: tuple[str, ...]
    conflicting_evidence: tuple[str, ...]
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
        if not isinstance(self.primary_setup, ExpertSetup):
            raise TypeError("primary_setup must be ExpertSetup.")
        if not isinstance(self.secondary_setup, ExpertSetup):
            raise TypeError("secondary_setup must be ExpertSetup.")
        if not isinstance(self.setup_strength, SetupStrength):
            raise TypeError("setup_strength must be SetupStrength.")
        if not isinstance(self.setup_quality, SetupQuality):
            raise TypeError("setup_quality must be SetupQuality.")
        if not isinstance(self.setup_stability, SetupStability):
            raise TypeError("setup_stability must be SetupStability.")
        object.__setattr__(self, "supporting_evidence", _normalize_text_tuple(self.supporting_evidence, "supporting_evidence"))
        object.__setattr__(self, "conflicting_evidence", _normalize_text_tuple(self.conflicting_evidence, "conflicting_evidence"))
        _validate_aware(self.timestamp, "timestamp")
        object.__setattr__(self, "source_fingerprint", _normalize_text(self.source_fingerprint, "source_fingerprint"))
        _validate_safety(self)


@dataclass(frozen=True, slots=True)
class ExpertSetupClassificationEngineSnapshot:
    enabled: bool
    lifecycle_state: SetupClassificationLifecycle
    classification_count: int
    updated_count: int
    partial_count: int
    invalid_count: int
    failed_count: int
    last_snapshot: ExpertSetupClassificationSnapshot | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool.")
        if not isinstance(self.lifecycle_state, SetupClassificationLifecycle):
            raise TypeError("lifecycle_state must be SetupClassificationLifecycle.")
        for field_name in ("classification_count", "updated_count", "partial_count", "invalid_count", "failed_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer.")
        if self.last_snapshot is not None and not isinstance(self.last_snapshot, ExpertSetupClassificationSnapshot):
            raise TypeError("last_snapshot must be ExpertSetupClassificationSnapshot or None.")
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


def _validate_safety(snapshot: ExpertSetupClassificationSnapshot) -> None:
    if snapshot.trade_decision_generated is not False:
        raise ValueError("setup classification must not generate trade decisions.")
    if snapshot.live_order_submission_enabled is not False:
        raise ValueError("setup classification must keep live order submission disabled.")
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
