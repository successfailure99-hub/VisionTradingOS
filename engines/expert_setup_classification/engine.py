"""
Expert Setup Classification Engine V1.
"""

from __future__ import annotations

import json
from datetime import datetime

from application.enums import RuntimeInstrument
from core import events
from core.base_engine import BaseEngine
from engines.market_state.enums import (
    MarketEvidenceQuality,
    MarketStability,
    MarketState,
    VolatilityState,
)
from engines.market_state.models import MarketStateSnapshot
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
    ExpertSetup,
    SetupClassificationLifecycle,
    SetupQuality,
    SetupStability,
    SetupStrength,
)
from .models import (
    ExpertSetupClassificationEngineSnapshot,
    ExpertSetupClassificationSnapshot,
)


class ExpertSetupClassificationEngine(BaseEngine):
    """
    Deterministic intelligence engine that labels the observable setup.

    The engine consumes only MultiTimeframeEvidenceSnapshot and
    MarketStateSnapshot values. It never inspects raw indicator engines,
    recalculates evidence, or produces trading intent.
    """

    def __init__(
        self,
        event_bus,
        *,
        instrument: RuntimeInstrument | str,
        maximum_source_age_seconds: int = 300,
    ) -> None:
        super().__init__(event_bus)
        self._instrument = _normalize_instrument(instrument)
        if (
            isinstance(maximum_source_age_seconds, bool)
            or not isinstance(maximum_source_age_seconds, int)
            or maximum_source_age_seconds < 0
        ):
            raise ValueError("maximum_source_age_seconds must be a non-negative integer.")
        self._maximum_source_age_seconds = maximum_source_age_seconds
        self._lifecycle_state = SetupClassificationLifecycle.CREATED
        self._last_snapshot: ExpertSetupClassificationSnapshot | None = None
        self._last_fingerprint: str | None = None
        self._classification_count = 0
        self._updated_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error: str | None = None

    @property
    def state(self) -> ExpertSetupClassificationSnapshot | None:
        return self._last_snapshot

    def start(self) -> ExpertSetupClassificationEngineSnapshot:
        self._lifecycle_state = SetupClassificationLifecycle.READY
        self._event_bus.publish(events.SETUP_CLASSIFICATION_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def stop(self) -> ExpertSetupClassificationEngineSnapshot:
        self._lifecycle_state = SetupClassificationLifecycle.STOPPED
        self._event_bus.publish(events.SETUP_CLASSIFICATION_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def classify(
        self,
        fusion: MultiTimeframeEvidenceSnapshot | None,
        market_state: MarketStateSnapshot | None,
        *,
        timestamp: datetime,
    ) -> ExpertSetupClassificationSnapshot:
        return self.process(fusion, market_state, timestamp=timestamp)

    def process(
        self,
        fusion: MultiTimeframeEvidenceSnapshot | None,
        market_state: MarketStateSnapshot | None,
        *,
        timestamp: datetime,
    ) -> ExpertSetupClassificationSnapshot:
        try:
            _validate_aware(timestamp, "timestamp")
            if fusion is None or market_state is None:
                snapshot = self._missing_snapshot(timestamp)
                partial = True
            else:
                self._validate_inputs(fusion, market_state)
                partial = _is_partial(fusion, market_state, timestamp, self._maximum_source_age_seconds)
                snapshot = self._build_snapshot(fusion, market_state, timestamp, partial=partial)
            if snapshot.source_fingerprint == self._last_fingerprint and self._last_snapshot is not None:
                return self._last_snapshot
        except (TypeError, ValueError):
            if self._last_error is None:
                self._last_error = "Setup classification input is invalid."
            self._invalid_count += 1
            self._event_bus.publish(events.SETUP_CLASSIFICATION_INVALID, self.snapshot())
            raise
        except Exception:
            self._failed_count += 1
            self._last_error = "Setup classification failed."
            self._lifecycle_state = SetupClassificationLifecycle.FAILED
            self._event_bus.publish(events.SETUP_CLASSIFICATION_FAILED, self.snapshot())
            raise

        self._last_snapshot = snapshot
        self._last_fingerprint = snapshot.source_fingerprint
        self._data = snapshot
        self._last_error = None
        self._classification_count += 1
        self._lifecycle_state = SetupClassificationLifecycle.ACTIVE
        if partial:
            self._partial_count += 1
            self._event_bus.publish(events.SETUP_CLASSIFICATION_PARTIAL, snapshot)
        else:
            self._updated_count += 1
            self._event_bus.publish(events.SETUP_CLASSIFICATION_UPDATED, snapshot)
        self._event_bus.publish(events.SETUP_CLASSIFICATION_STATE_UPDATED, self.snapshot())
        return snapshot

    def snapshot(self) -> ExpertSetupClassificationEngineSnapshot:
        return ExpertSetupClassificationEngineSnapshot(
            enabled=True,
            lifecycle_state=self._lifecycle_state,
            classification_count=self._classification_count,
            updated_count=self._updated_count,
            partial_count=self._partial_count,
            invalid_count=self._invalid_count,
            failed_count=self._failed_count,
            last_snapshot=self._last_snapshot,
            last_error=self._last_error,
        )

    def reset(self) -> ExpertSetupClassificationEngineSnapshot:
        super().clear()
        self._lifecycle_state = SetupClassificationLifecycle.READY
        self._last_snapshot = None
        self._last_fingerprint = None
        self._classification_count = 0
        self._updated_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error = None
        self._event_bus.publish(events.SETUP_CLASSIFICATION_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def clear(self) -> None:
        self.reset()

    def _validate_inputs(
        self,
        fusion: MultiTimeframeEvidenceSnapshot,
        market_state: MarketStateSnapshot,
    ) -> None:
        if not isinstance(fusion, MultiTimeframeEvidenceSnapshot):
            self._last_error = "Setup classification requires MultiTimeframeEvidenceSnapshot input."
            raise TypeError(self._last_error)
        if not isinstance(market_state, MarketStateSnapshot):
            self._last_error = "Setup classification requires MarketStateSnapshot input."
            raise TypeError(self._last_error)
        if fusion.instrument is not self._instrument or market_state.instrument is not self._instrument:
            self._last_error = "Setup classification input instrument does not match engine."
            raise ValueError(self._last_error)

    def _missing_snapshot(self, timestamp: datetime) -> ExpertSetupClassificationSnapshot:
        payload = {
            "instrument": self._instrument.value,
            "missing": True,
            "primary": ExpertSetup.NO_QUALITY_SETUP.value,
            "partial": True,
        }
        return ExpertSetupClassificationSnapshot(
            trading_date=timestamp.date(),
            instrument=self._instrument,
            primary_setup=ExpertSetup.NO_QUALITY_SETUP,
            secondary_setup=ExpertSetup.NO_QUALITY_SETUP,
            setup_strength=SetupStrength.WEAK,
            setup_quality=SetupQuality.LOW,
            setup_stability=SetupStability.UNSTABLE,
            supporting_evidence=("missing_fusion_or_market_state",),
            conflicting_evidence=(),
            timestamp=timestamp,
            source_fingerprint=_fingerprint(payload),
        )

    def _build_snapshot(
        self,
        fusion: MultiTimeframeEvidenceSnapshot,
        market_state: MarketStateSnapshot,
        timestamp: datetime,
        *,
        partial: bool,
    ) -> ExpertSetupClassificationSnapshot:
        primary = _primary_setup(fusion, market_state, partial)
        secondary = _secondary_setup(fusion, market_state, primary)
        strength = _strength(fusion, market_state, partial)
        quality = _quality(fusion, market_state, partial)
        stability = _stability(fusion, market_state, partial)
        if self._last_snapshot is not None and _should_preserve_previous_setup(
            self._last_snapshot,
            primary,
            stability,
            fusion,
            market_state,
            partial,
        ):
            primary = self._last_snapshot.primary_setup
            secondary = self._last_snapshot.secondary_setup
            strength = self._last_snapshot.setup_strength
            quality = self._last_snapshot.setup_quality
            stability = self._last_snapshot.setup_stability
        supporting = _supporting_evidence(fusion, market_state, primary, partial)
        conflicting = _conflicting_evidence(fusion, market_state, partial)
        payload = {
            "primary": primary.value,
            "secondary": secondary.value,
            "strength": strength.value,
            "quality": quality.value,
            "stability": stability.value,
            "supporting": supporting,
            "conflicting": conflicting,
            "partial": partial,
        }
        return ExpertSetupClassificationSnapshot(
            trading_date=timestamp.date(),
            instrument=self._instrument,
            primary_setup=primary,
            secondary_setup=secondary,
            setup_strength=strength,
            setup_quality=quality,
            setup_stability=stability,
            supporting_evidence=supporting,
            conflicting_evidence=conflicting,
            timestamp=timestamp,
            source_fingerprint=_fingerprint(payload),
        )


def _primary_setup(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    partial: bool,
) -> ExpertSetup:
    if partial or fusion.evidence_completeness is not EvidenceCompleteness.COMPLETE:
        return ExpertSetup.NO_QUALITY_SETUP
    direction = _dominant_direction(fusion)
    if market_state.market_state is MarketState.VOLATILE:
        return ExpertSetup.FAILED_BREAKOUT
    if _is_trap_candidate(fusion, market_state) and direction is FusionDirection.BULLISH:
        return ExpertSetup.BULL_TRAP
    if _is_trap_candidate(fusion, market_state) and direction is FusionDirection.BEARISH:
        return ExpertSetup.BEAR_TRAP
    if market_state.market_state is MarketState.COMPRESSION:
        return ExpertSetup.COMPRESSION
    if market_state.market_state is MarketState.EXPANSION:
        return ExpertSetup.EXPANSION
    if market_state.market_state is MarketState.RANGING:
        return ExpertSetup.RANGE_DAY
    if market_state.market_state is MarketState.TRENDING:
        if fusion.alignment_score >= 90 and market_state.confidence_level.value == "high_structure":
            return ExpertSetup.TREND_DAY
        return ExpertSetup.TREND_CONTINUATION
    if market_state.market_state is MarketState.TRANSITION:
        if fusion.evidence_conflict is EvidenceConflict.MINOR:
            return ExpertSetup.BREAKOUT
        if fusion.evidence_conflict is EvidenceConflict.MAJOR:
            return ExpertSetup.REVERSAL_ATTEMPT
        return ExpertSetup.PULLBACK_CONTINUATION
    if fusion.weak_timeframes and fusion.conflicting_timeframes:
        return ExpertSetup.LIQUIDITY_SWEEP
    return ExpertSetup.NO_QUALITY_SETUP


def _secondary_setup(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    primary: ExpertSetup,
) -> ExpertSetup:
    if primary in {ExpertSetup.NO_QUALITY_SETUP, ExpertSetup.BULL_TRAP, ExpertSetup.BEAR_TRAP}:
        return ExpertSetup.NO_QUALITY_SETUP
    if market_state.market_state is MarketState.TRENDING and fusion.weak_timeframes:
        return ExpertSetup.PULLBACK_CONTINUATION
    if market_state.market_state is MarketState.EXPANSION:
        return ExpertSetup.BREAKOUT
    if market_state.market_state is MarketState.COMPRESSION:
        return ExpertSetup.BREAKOUT
    if fusion.conflicting_timeframes:
        return ExpertSetup.REVERSAL_ATTEMPT
    return ExpertSetup.NO_QUALITY_SETUP


def _strength(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    partial: bool,
) -> SetupStrength:
    if partial or fusion.evidence_completeness is not EvidenceCompleteness.COMPLETE:
        return SetupStrength.WEAK
    if (
        fusion.alignment_score >= 80
        and fusion.conflict_score <= 20
        and market_state.market_stability is MarketStability.STABLE
    ):
        return SetupStrength.STRONG
    if fusion.alignment_score >= 50 and fusion.conflict_score <= 50:
        return SetupStrength.MODERATE
    return SetupStrength.WEAK


def _quality(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    partial: bool,
) -> SetupQuality:
    if partial or market_state.evidence_quality in {MarketEvidenceQuality.LOW, MarketEvidenceQuality.INSUFFICIENT}:
        return SetupQuality.LOW
    if (
        market_state.evidence_quality is MarketEvidenceQuality.HIGH
        and fusion.evidence_conflict is EvidenceConflict.NONE
    ):
        return SetupQuality.HIGH
    return SetupQuality.MEDIUM


def _stability(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    partial: bool,
) -> SetupStability:
    if partial or market_state.market_stability is MarketStability.UNSTABLE:
        return SetupStability.UNSTABLE
    if market_state.market_stability is MarketStability.CHANGING or fusion.evidence_conflict is EvidenceConflict.MINOR:
        return SetupStability.CHANGING
    return SetupStability.STABLE


def _supporting_evidence(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    primary: ExpertSetup,
    partial: bool,
) -> tuple[str, ...]:
    values = [
        f"market_state:{market_state.market_state.value}",
        f"agreement:{fusion.evidence_agreement.value}",
        f"dominant_timeframe:{fusion.dominant_timeframe}",
    ]
    if partial:
        values.append("partial_inputs")
    if primary is not ExpertSetup.NO_QUALITY_SETUP:
        values.append(f"primary_setup:{primary.value}")
    return tuple(values)


def _conflicting_evidence(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    partial: bool,
) -> tuple[str, ...]:
    values: list[str] = []
    if partial:
        values.append("incomplete_inputs")
    if fusion.conflicting_timeframes:
        values.append("conflicting_timeframes:" + ",".join(fusion.conflicting_timeframes))
    if fusion.weak_timeframes:
        values.append("weak_timeframes:" + ",".join(fusion.weak_timeframes))
    if market_state.volatility_state is VolatilityState.VOLATILE:
        values.append("volatile_market_state")
    return tuple(values)


def _dominant_direction(fusion: MultiTimeframeEvidenceSnapshot) -> FusionDirection:
    directions = {summary.timeframe: summary.direction for summary in fusion.summaries}
    if fusion.dominant_timeframe in directions:
        return directions[fusion.dominant_timeframe]
    return FusionDirection.UNKNOWN


def _is_trap_candidate(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
) -> bool:
    return (
        market_state.market_state in {MarketState.VOLATILE, MarketState.TRANSITION}
        and fusion.evidence_conflict is EvidenceConflict.MAJOR
        and bool(fusion.conflicting_timeframes)
    )


def _is_partial(
    fusion: MultiTimeframeEvidenceSnapshot | None,
    market_state: MarketStateSnapshot | None,
    timestamp: datetime,
    maximum_source_age_seconds: int,
) -> bool:
    if fusion is None or market_state is None:
        return True
    return (
        fusion.evidence_completeness is not EvidenceCompleteness.COMPLETE
        or market_state.evidence_quality in {MarketEvidenceQuality.LOW, MarketEvidenceQuality.INSUFFICIENT}
        or (timestamp - fusion.timestamp).total_seconds() > maximum_source_age_seconds
        or (timestamp - market_state.timestamp).total_seconds() > maximum_source_age_seconds
    )


_NOISY_TRANSITIONS = {
    frozenset((ExpertSetup.BREAKOUT, ExpertSetup.FAILED_BREAKOUT)),
    frozenset((ExpertSetup.TREND_CONTINUATION, ExpertSetup.PULLBACK_CONTINUATION)),
    frozenset((ExpertSetup.TREND_DAY, ExpertSetup.RANGE_DAY)),
}


def _should_preserve_previous_setup(
    previous: ExpertSetupClassificationSnapshot,
    candidate: ExpertSetup,
    candidate_stability: SetupStability,
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    partial: bool,
) -> bool:
    if partial:
        return False
    if previous.primary_setup is candidate:
        return False
    if previous.primary_setup is ExpertSetup.NO_QUALITY_SETUP:
        return False
    if _is_material_setup_change(fusion, market_state):
        return False
    pair = frozenset((previous.primary_setup, candidate))
    if pair in _NOISY_TRANSITIONS:
        return True
    return previous.setup_stability is SetupStability.STABLE and candidate_stability is not SetupStability.STABLE


def _is_material_setup_change(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
) -> bool:
    return (
        fusion.evidence_conflict is EvidenceConflict.MAJOR
        and fusion.conflict_score >= 50
        and market_state.volatility_state is VolatilityState.VOLATILE
    )


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
