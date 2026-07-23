"""
Immutable Market State Engine V1 models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from application.enums import RuntimeInstrument

from .enums import (
    MarketEvidenceQuality,
    MarketPhase,
    MarketStability,
    MarketState,
    MarketStateLifecycle,
    StructuralConfidence,
    VolatilityState,
)


@dataclass(frozen=True, slots=True)
class MarketStateSnapshot:
    trading_date: date
    instrument: RuntimeInstrument
    market_state: MarketState
    market_phase: MarketPhase
    market_stability: MarketStability
    volatility_state: VolatilityState
    evidence_quality: MarketEvidenceQuality
    confidence_level: StructuralConfidence
    dominant_timeframe: str
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
        if not isinstance(self.market_state, MarketState):
            raise TypeError("market_state must be MarketState.")
        if not isinstance(self.market_phase, MarketPhase):
            raise TypeError("market_phase must be MarketPhase.")
        if not isinstance(self.market_stability, MarketStability):
            raise TypeError("market_stability must be MarketStability.")
        if not isinstance(self.volatility_state, VolatilityState):
            raise TypeError("volatility_state must be VolatilityState.")
        if not isinstance(self.evidence_quality, MarketEvidenceQuality):
            raise TypeError("evidence_quality must be MarketEvidenceQuality.")
        if not isinstance(self.confidence_level, StructuralConfidence):
            raise TypeError("confidence_level must be StructuralConfidence.")
        object.__setattr__(self, "dominant_timeframe", _normalize_text(self.dominant_timeframe, "dominant_timeframe"))
        _validate_aware(self.timestamp, "timestamp")
        object.__setattr__(self, "source_fingerprint", _normalize_text(self.source_fingerprint, "source_fingerprint"))
        _validate_safety(self)


@dataclass(frozen=True, slots=True)
class MarketStateEngineSnapshot:
    enabled: bool
    lifecycle_state: MarketStateLifecycle
    evaluation_count: int
    updated_count: int
    partial_count: int
    invalid_count: int
    failed_count: int
    last_snapshot: MarketStateSnapshot | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool.")
        if not isinstance(self.lifecycle_state, MarketStateLifecycle):
            raise TypeError("lifecycle_state must be MarketStateLifecycle.")
        for field_name in ("evaluation_count", "updated_count", "partial_count", "invalid_count", "failed_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer.")
        if self.last_snapshot is not None and not isinstance(self.last_snapshot, MarketStateSnapshot):
            raise TypeError("last_snapshot must be MarketStateSnapshot or None.")
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


def _validate_safety(snapshot: MarketStateSnapshot) -> None:
    if snapshot.trade_decision_generated is not False:
        raise ValueError("market state must not generate trade decisions.")
    if snapshot.live_order_submission_enabled is not False:
        raise ValueError("market state must keep live order submission disabled.")
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
