"""
Market State Engine V1.
"""

from __future__ import annotations

import json
from datetime import datetime

from application.enums import RuntimeInstrument
from core import events
from core.base_engine import BaseEngine
from engines.multi_timeframe_evidence_fusion.enums import (
    EvidenceAgreement,
    EvidenceCompleteness,
    EvidenceConflict,
    FusionDirection,
)
from engines.multi_timeframe_evidence_fusion.models import (
    MultiTimeframeEvidenceSnapshot,
)

from .enums import (
    MarketEvidenceQuality,
    MarketPhase,
    MarketStability,
    MarketState,
    MarketStateLifecycle,
    StructuralConfidence,
    VolatilityState,
)
from .models import MarketStateEngineSnapshot, MarketStateSnapshot


class MarketStateEngine(BaseEngine):
    """
    Deterministic intelligence engine that describes the market environment.

    The engine consumes only MultiTimeframeEvidenceSnapshot values. It does not
    calculate indicators, infer intent, call strategy/risk/execution layers, or
    inspect raw evidence engine internals.
    """

    def __init__(
        self,
        event_bus,
        *,
        instrument: RuntimeInstrument | str,
        maximum_fusion_age_seconds: int = 300,
    ) -> None:
        super().__init__(event_bus)
        self._instrument = _normalize_instrument(instrument)
        if (
            isinstance(maximum_fusion_age_seconds, bool)
            or not isinstance(maximum_fusion_age_seconds, int)
            or maximum_fusion_age_seconds < 0
        ):
            raise ValueError("maximum_fusion_age_seconds must be a non-negative integer.")
        self._maximum_fusion_age_seconds = maximum_fusion_age_seconds
        self._lifecycle_state = MarketStateLifecycle.CREATED
        self._last_snapshot: MarketStateSnapshot | None = None
        self._last_observable_fingerprint: str | None = None
        self._evaluation_count = 0
        self._updated_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error: str | None = None

    @property
    def state(self) -> MarketStateSnapshot | None:
        return self._last_snapshot

    def start(self) -> MarketStateEngineSnapshot:
        self._lifecycle_state = MarketStateLifecycle.READY
        self._event_bus.publish(events.MARKET_STATE_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def stop(self) -> MarketStateEngineSnapshot:
        self._lifecycle_state = MarketStateLifecycle.STOPPED
        self._event_bus.publish(events.MARKET_STATE_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def process(
        self,
        fusion: MultiTimeframeEvidenceSnapshot | None,
        *,
        timestamp: datetime,
    ) -> MarketStateSnapshot:
        return self.update(fusion, timestamp=timestamp)

    def update(
        self,
        fusion: MultiTimeframeEvidenceSnapshot | None,
        *,
        timestamp: datetime,
    ) -> MarketStateSnapshot:
        try:
            _validate_aware(timestamp, "timestamp")
            if fusion is None:
                snapshot = self._missing_snapshot(timestamp)
                partial = True
            else:
                self._validate_fusion(fusion)
                partial = _is_stale(fusion, timestamp, self._maximum_fusion_age_seconds) or (
                    fusion.evidence_completeness is not EvidenceCompleteness.COMPLETE
                )
                snapshot = self._build_snapshot(fusion, timestamp, partial=partial)
            if snapshot.source_fingerprint == self._last_observable_fingerprint and self._last_snapshot is not None:
                return self._last_snapshot
        except (TypeError, ValueError):
            if self._last_error is None:
                self._last_error = "Market state input is invalid."
            self._invalid_count += 1
            self._event_bus.publish(events.MARKET_STATE_INVALID, self.snapshot())
            raise
        except Exception:
            self._failed_count += 1
            self._last_error = "Market state evaluation failed."
            self._lifecycle_state = MarketStateLifecycle.FAILED
            self._event_bus.publish(events.MARKET_STATE_FAILED, self.snapshot())
            raise

        self._last_snapshot = snapshot
        self._last_observable_fingerprint = snapshot.source_fingerprint
        self._data = snapshot
        self._last_error = None
        self._evaluation_count += 1
        self._lifecycle_state = MarketStateLifecycle.ACTIVE
        if partial:
            self._partial_count += 1
            self._event_bus.publish(events.MARKET_STATE_PARTIAL, snapshot)
        else:
            self._updated_count += 1
            self._event_bus.publish(events.MARKET_STATE_UPDATED, snapshot)
        self._event_bus.publish(events.MARKET_STATE_STATE_UPDATED, self.snapshot())
        return snapshot

    def snapshot(self) -> MarketStateEngineSnapshot:
        return MarketStateEngineSnapshot(
            enabled=True,
            lifecycle_state=self._lifecycle_state,
            evaluation_count=self._evaluation_count,
            updated_count=self._updated_count,
            partial_count=self._partial_count,
            invalid_count=self._invalid_count,
            failed_count=self._failed_count,
            last_snapshot=self._last_snapshot,
            last_error=self._last_error,
        )

    def reset(self) -> MarketStateEngineSnapshot:
        super().clear()
        self._lifecycle_state = MarketStateLifecycle.READY
        self._last_snapshot = None
        self._last_observable_fingerprint = None
        self._evaluation_count = 0
        self._updated_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error = None
        self._event_bus.publish(events.MARKET_STATE_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def clear(self) -> None:
        self.reset()

    def _validate_fusion(self, fusion: MultiTimeframeEvidenceSnapshot) -> None:
        if not isinstance(fusion, MultiTimeframeEvidenceSnapshot):
            self._last_error = "Market state requires MultiTimeframeEvidenceSnapshot input."
            raise TypeError(self._last_error)
        if fusion.instrument is not self._instrument:
            self._last_error = "Fusion instrument does not match market state engine."
            raise ValueError(self._last_error)

    def _missing_snapshot(self, timestamp: datetime) -> MarketStateSnapshot:
        payload = {
            "instrument": self._instrument.value,
            "missing": "multi_timeframe_evidence",
            "partial": True,
        }
        return MarketStateSnapshot(
            trading_date=timestamp.date(),
            instrument=self._instrument,
            market_state=MarketState.BALANCED,
            market_phase=MarketPhase.EARLY,
            market_stability=MarketStability.CHANGING,
            volatility_state=VolatilityState.QUIET,
            evidence_quality=MarketEvidenceQuality.INSUFFICIENT,
            confidence_level=StructuralConfidence.LOW_STRUCTURE,
            dominant_timeframe="NONE",
            timestamp=timestamp,
            source_fingerprint=_fingerprint(payload),
        )

    def _build_snapshot(
        self,
        fusion: MultiTimeframeEvidenceSnapshot,
        timestamp: datetime,
        *,
        partial: bool,
    ) -> MarketStateSnapshot:
        quality = _evidence_quality(fusion, partial)
        market_state = _market_state(fusion, partial)
        phase = _market_phase(fusion, market_state, quality)
        stability = _market_stability(fusion, market_state, partial)
        volatility = _volatility_state(fusion, market_state)
        confidence = _confidence(quality, stability)
        if self._last_snapshot is not None and _should_preserve_previous_state(
            self._last_snapshot,
            market_state,
            fusion,
            partial,
        ):
            market_state = self._last_snapshot.market_state
            phase = self._last_snapshot.market_phase
            stability = self._last_snapshot.market_stability
            volatility = self._last_snapshot.volatility_state
            quality = self._last_snapshot.evidence_quality
            confidence = self._last_snapshot.confidence_level
        payload = {
            "market_state": market_state.value,
            "market_phase": phase.value,
            "stability": stability.value,
            "volatility": volatility.value,
            "quality": quality.value,
            "confidence": confidence.value,
            "dominant_timeframe": fusion.dominant_timeframe,
            "partial": partial,
        }
        return MarketStateSnapshot(
            trading_date=timestamp.date(),
            instrument=self._instrument,
            market_state=market_state,
            market_phase=phase,
            market_stability=stability,
            volatility_state=volatility,
            evidence_quality=quality,
            confidence_level=confidence,
            dominant_timeframe=fusion.dominant_timeframe,
            timestamp=timestamp,
            source_fingerprint=_fingerprint(payload),
        )


def _market_state(fusion: MultiTimeframeEvidenceSnapshot, partial: bool) -> MarketState:
    if fusion.evidence_completeness is EvidenceCompleteness.INSUFFICIENT:
        return MarketState.BALANCED
    if partial:
        return MarketState.TRANSITION
    if fusion.evidence_conflict is EvidenceConflict.MAJOR:
        return MarketState.VOLATILE
    directions = tuple(summary.direction for summary in fusion.summaries)
    if directions and all(direction is FusionDirection.NEUTRAL for direction in directions):
        return MarketState.RANGING
    if not fusion.aligned_timeframes and not fusion.conflicting_timeframes and fusion.weak_timeframes:
        return MarketState.QUIET
    if fusion.weak_timeframes and fusion.evidence_conflict is EvidenceConflict.NONE:
        return MarketState.COMPRESSION
    if fusion.evidence_agreement is EvidenceAgreement.FULL_ALIGNMENT and fusion.conflict_score == 0:
        return MarketState.TRENDING
    if fusion.evidence_agreement is EvidenceAgreement.PARTIAL_ALIGNMENT and fusion.evidence_conflict is EvidenceConflict.MINOR:
        return MarketState.EXPANSION
    if fusion.evidence_agreement in {EvidenceAgreement.MIXED, EvidenceAgreement.CONFLICT}:
        return MarketState.TRANSITION
    return MarketState.BALANCED


def _market_phase(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketState,
    quality: MarketEvidenceQuality,
) -> MarketPhase:
    if market_state is MarketState.VOLATILE or fusion.evidence_conflict is EvidenceConflict.MAJOR:
        return MarketPhase.EXHAUSTING
    if quality is MarketEvidenceQuality.INSUFFICIENT:
        return MarketPhase.EARLY
    if market_state in {MarketState.TRANSITION, MarketState.EXPANSION, MarketState.COMPRESSION}:
        return MarketPhase.DEVELOPING
    if quality is MarketEvidenceQuality.HIGH and fusion.alignment_score >= 80:
        return MarketPhase.MATURE
    return MarketPhase.DEVELOPING


def _market_stability(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketState,
    partial: bool,
) -> MarketStability:
    if market_state is MarketState.VOLATILE or fusion.evidence_conflict is EvidenceConflict.MAJOR:
        return MarketStability.UNSTABLE
    if partial or market_state in {MarketState.TRANSITION, MarketState.EXPANSION, MarketState.COMPRESSION}:
        return MarketStability.CHANGING
    return MarketStability.STABLE


def _volatility_state(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketState,
) -> VolatilityState:
    if market_state is MarketState.VOLATILE or fusion.conflict_score >= 50:
        return VolatilityState.VOLATILE
    if market_state in {MarketState.QUIET, MarketState.RANGING} and fusion.conflict_score == 0:
        return VolatilityState.QUIET
    return VolatilityState.NORMAL


def _evidence_quality(
    fusion: MultiTimeframeEvidenceSnapshot,
    partial: bool,
) -> MarketEvidenceQuality:
    if fusion.evidence_completeness is EvidenceCompleteness.INSUFFICIENT:
        return MarketEvidenceQuality.INSUFFICIENT
    if partial:
        return MarketEvidenceQuality.LOW
    if fusion.alignment_score >= 80 and fusion.conflict_score <= 20:
        return MarketEvidenceQuality.HIGH
    if fusion.alignment_score >= 50:
        return MarketEvidenceQuality.MEDIUM
    return MarketEvidenceQuality.LOW


def _confidence(
    quality: MarketEvidenceQuality,
    stability: MarketStability,
) -> StructuralConfidence:
    if quality is MarketEvidenceQuality.HIGH and stability is MarketStability.STABLE:
        return StructuralConfidence.HIGH_STRUCTURE
    if quality in {MarketEvidenceQuality.HIGH, MarketEvidenceQuality.MEDIUM}:
        return StructuralConfidence.MEDIUM_STRUCTURE
    return StructuralConfidence.LOW_STRUCTURE


def _should_preserve_previous_state(
    previous: MarketStateSnapshot,
    candidate: MarketState,
    fusion: MultiTimeframeEvidenceSnapshot,
    partial: bool,
) -> bool:
    if partial:
        return False
    if previous.evidence_quality is MarketEvidenceQuality.INSUFFICIENT:
        return False
    if previous.market_state not in {MarketState.TRENDING, MarketState.RANGING}:
        return False
    if candidate not in {MarketState.TRANSITION, MarketState.EXPANSION, MarketState.COMPRESSION}:
        return False
    if fusion.evidence_conflict is EvidenceConflict.MAJOR:
        return False
    return True


def _is_stale(
    fusion: MultiTimeframeEvidenceSnapshot,
    timestamp: datetime,
    maximum_age_seconds: int,
) -> bool:
    return (timestamp - fusion.timestamp).total_seconds() > maximum_age_seconds


def _normalize_instrument(value: RuntimeInstrument | str) -> RuntimeInstrument:
    if isinstance(value, RuntimeInstrument):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        for instrument in RuntimeInstrument:
            if instrument.value == normalized or instrument.name == normalized:
                return instrument
    raise ValueError("instrument must be a RuntimeInstrument.")


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _fingerprint(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
