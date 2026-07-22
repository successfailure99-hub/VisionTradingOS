"""
Multi-Timeframe Evidence Fusion Engine V1.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Iterable

from application.enums import RuntimeInstrument
from core import events
from core.base_engine import BaseEngine
from core.enums.timeframe import TimeFrame
from engines.market_context.enums import MarketBias
from engines.market_context.models import MarketContextState
from engines.price_action.enums import Trend
from engines.price_action.models import PriceActionState
from engines.tradingview_evidence.enums import EvidenceAvailability
from engines.tradingview_evidence.models import TradingViewEvidenceSnapshot

from .enums import (
    EvidenceAgreement,
    EvidenceCompleteness,
    EvidenceConflict,
    FusionDirection,
    FusionLifecycle,
)
from .models import (
    MultiTimeframeEvidenceFusionSnapshot,
    MultiTimeframeEvidenceSnapshot,
    TimeframeEvidenceSummary,
)


_TIMEFRAME_PRIORITY = {
    "1D": 60,
    "30m": 50,
    "15m": 40,
    "5m": 30,
    "3m": 20,
    "1m": 10,
}


class MultiTimeframeEvidenceFusionEngine(BaseEngine):
    """
    Deterministically compares already-mapped TradingView evidence lanes.

    The engine owns no market data and performs no indicator calculations. It
    consumes immutable TradingViewEvidenceSnapshot values and publishes one
    immutable market-understanding snapshot per observable evidence change.
    """

    def __init__(
        self,
        event_bus,
        *,
        instrument: RuntimeInstrument | str,
        expected_timeframes: Iterable[str | TimeFrame],
        maximum_source_age_seconds: int = 300,
    ) -> None:
        super().__init__(event_bus)
        self._instrument = _normalize_instrument(instrument)
        self._expected_timeframes = _normalize_timeframes(expected_timeframes)
        if (
            isinstance(maximum_source_age_seconds, bool)
            or not isinstance(maximum_source_age_seconds, int)
            or maximum_source_age_seconds < 0
        ):
            raise ValueError("maximum_source_age_seconds must be a non-negative integer.")
        self._maximum_source_age_seconds = maximum_source_age_seconds
        self._lifecycle_state = FusionLifecycle.CREATED
        self._last_snapshot: MultiTimeframeEvidenceSnapshot | None = None
        self._last_fingerprint: str | None = None
        self._fusion_count = 0
        self._updated_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error: str | None = None

    @property
    def state(self) -> MultiTimeframeEvidenceSnapshot | None:
        return self._last_snapshot

    @property
    def expected_timeframes(self) -> tuple[str, ...]:
        return self._expected_timeframes

    def start(self) -> MultiTimeframeEvidenceFusionSnapshot:
        self._lifecycle_state = FusionLifecycle.READY
        self._event_bus.publish(events.MULTI_TIMEFRAME_EVIDENCE_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def stop(self) -> MultiTimeframeEvidenceFusionSnapshot:
        self._lifecycle_state = FusionLifecycle.STOPPED
        self._event_bus.publish(events.MULTI_TIMEFRAME_EVIDENCE_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def fuse(
        self,
        evidence: Iterable[TradingViewEvidenceSnapshot],
        *,
        timestamp: datetime | None = None,
    ) -> MultiTimeframeEvidenceSnapshot:
        try:
            snapshots = tuple(evidence)
            self._validate_synthetic_input(snapshots, timestamp)
            request_timestamp = timestamp or max(item.timestamp for item in snapshots)
            summaries = tuple(
                _summary(item, request_timestamp, self._maximum_source_age_seconds)
                for item in _sort_evidence(snapshots)
            )
            missing_timeframes = tuple(timeframe for timeframe in self._expected_timeframes if timeframe not in {item.timeframe for item in summaries})
            snapshot = self._build_snapshot(summaries, missing_timeframes, request_timestamp)
            if snapshot.source_fingerprint == self._last_fingerprint and self._last_snapshot is not None:
                return self._last_snapshot
        except (TypeError, ValueError):
            if self._last_error is None:
                self._last_error = "Multi-timeframe evidence input is invalid."
            self._invalid_count += 1
            self._event_bus.publish(events.MULTI_TIMEFRAME_EVIDENCE_INVALID, self.snapshot())
            raise
        except Exception:
            self._failed_count += 1
            self._last_error = "Multi-timeframe evidence fusion failed."
            self._lifecycle_state = FusionLifecycle.FAILED
            self._event_bus.publish(events.MULTI_TIMEFRAME_EVIDENCE_FAILED, self.snapshot())
            raise

        self._last_snapshot = snapshot
        self._last_fingerprint = snapshot.source_fingerprint
        self._data = snapshot
        self._last_error = None
        self._fusion_count += 1
        self._lifecycle_state = FusionLifecycle.ACTIVE
        if snapshot.evidence_completeness is EvidenceCompleteness.COMPLETE:
            self._updated_count += 1
            self._event_bus.publish(events.MULTI_TIMEFRAME_EVIDENCE_UPDATED, snapshot)
        else:
            self._partial_count += 1
            self._event_bus.publish(events.MULTI_TIMEFRAME_EVIDENCE_PARTIAL, snapshot)
        self._event_bus.publish(events.MULTI_TIMEFRAME_EVIDENCE_STATE_UPDATED, self.snapshot())
        return snapshot

    def snapshot(self) -> MultiTimeframeEvidenceFusionSnapshot:
        return MultiTimeframeEvidenceFusionSnapshot(
            enabled=True,
            lifecycle_state=self._lifecycle_state,
            fusion_count=self._fusion_count,
            updated_count=self._updated_count,
            partial_count=self._partial_count,
            invalid_count=self._invalid_count,
            failed_count=self._failed_count,
            last_snapshot=self._last_snapshot,
            last_error=self._last_error,
        )

    def reset(self) -> MultiTimeframeEvidenceFusionSnapshot:
        super().clear()
        self._lifecycle_state = FusionLifecycle.READY
        self._last_snapshot = None
        self._last_fingerprint = None
        self._fusion_count = 0
        self._updated_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error = None
        self._event_bus.publish(events.MULTI_TIMEFRAME_EVIDENCE_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def clear(self) -> None:
        self.reset()

    def _validate_synthetic_input(
        self,
        snapshots: tuple[TradingViewEvidenceSnapshot, ...],
        timestamp: datetime | None,
    ) -> None:
        if not snapshots:
            self._last_error = "At least one TradingView evidence snapshot is required."
            raise ValueError(self._last_error)
        if timestamp is not None:
            _validate_aware(timestamp, "timestamp")
        seen: set[str] = set()
        for item in snapshots:
            if not isinstance(item, TradingViewEvidenceSnapshot):
                self._last_error = "Fusion input must contain TradingViewEvidenceSnapshot values."
                raise TypeError(self._last_error)
            if item.instrument is not self._instrument:
                self._last_error = "TradingView evidence instrument does not match fusion engine."
                raise ValueError(self._last_error)
            if item.timeframe not in self._expected_timeframes:
                self._last_error = "TradingView evidence timeframe is not configured for fusion."
                raise ValueError(self._last_error)
            if item.timeframe in seen:
                self._last_error = "Duplicate TradingView evidence timeframe received."
                raise ValueError(self._last_error)
            seen.add(item.timeframe)

    def _build_snapshot(
        self,
        summaries: tuple[TimeframeEvidenceSummary, ...],
        missing_timeframes: tuple[str, ...],
        timestamp: datetime,
    ) -> MultiTimeframeEvidenceSnapshot:
        available = tuple(item.timeframe for item in summaries if item.completeness is EvidenceCompleteness.COMPLETE)
        invalid = tuple(item.timeframe for item in summaries if item.invalid_evidence)
        stale = tuple(item.timeframe for item in summaries if item.stale_evidence)
        weak = tuple(
            item.timeframe
            for item in summaries
            if item.direction in {FusionDirection.MIXED, FusionDirection.UNKNOWN}
            or item.completeness is not EvidenceCompleteness.COMPLETE
        )
        directions = {item.timeframe: item.direction for item in summaries if item.direction in _DIRECTIONAL}
        dominant_direction, aligned, conflicting = _alignment(directions)
        completeness = _completeness(summaries, missing_timeframes)
        agreement = _agreement(directions, aligned, conflicting, completeness)
        conflict = _conflict(conflicting, directions, completeness)
        expected_count = len(self._expected_timeframes)
        alignment_score = round((len(aligned) / expected_count) * 100, 2) if expected_count else 0.0
        conflict_score = round((len(conflicting) / expected_count) * 100, 2) if expected_count else 0.0
        dominant_timeframe = _dominant_timeframe(aligned, summaries) if dominant_direction is not FusionDirection.UNKNOWN else "NONE"
        payload = {
            "expected_timeframes": self._expected_timeframes,
            "summaries": [
                {
                    "timeframe": item.timeframe,
                    "direction": item.direction.value,
                    "completeness": item.completeness.value,
                    "missing": item.missing_evidence,
                    "invalid": item.invalid_evidence,
                    "stale": item.stale_evidence,
                    "timestamp": item.timestamp.isoformat(),
                    "source": item.source_fingerprint,
                }
                for item in summaries
            ],
            "missing_timeframes": missing_timeframes,
            "agreement": agreement.value,
            "conflict": conflict.value,
            "dominant_timeframe": dominant_timeframe,
            "alignment_score": alignment_score,
            "conflict_score": conflict_score,
            "completeness": completeness.value,
        }
        return MultiTimeframeEvidenceSnapshot(
            trading_date=timestamp.date(),
            instrument=self._instrument,
            timeframes=self._expected_timeframes,
            evidence_agreement=agreement,
            evidence_conflict=conflict,
            dominant_timeframe=dominant_timeframe,
            alignment_score=alignment_score,
            conflict_score=conflict_score,
            evidence_completeness=completeness,
            timestamp=timestamp,
            summaries=summaries,
            available_timeframes=available,
            missing_timeframes=missing_timeframes,
            invalid_timeframes=invalid,
            stale_timeframes=stale,
            aligned_timeframes=aligned,
            conflicting_timeframes=conflicting,
            weak_timeframes=weak,
            source_fingerprint=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        )


_DIRECTIONAL = {FusionDirection.BULLISH, FusionDirection.BEARISH, FusionDirection.NEUTRAL}


def _normalize_instrument(value: RuntimeInstrument | str) -> RuntimeInstrument:
    if isinstance(value, RuntimeInstrument):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        for instrument in RuntimeInstrument:
            if instrument.value == normalized or instrument.name == normalized:
                return instrument
    raise ValueError("instrument must be a RuntimeInstrument.")


def _normalize_timeframes(values: Iterable[str | TimeFrame]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        timeframe = value.value if isinstance(value, TimeFrame) else str(value).strip()
        TimeFrame.from_value(timeframe)
        if timeframe in result:
            raise ValueError("expected_timeframes must be unique.")
        result.append(timeframe)
    if not result:
        raise ValueError("expected_timeframes must not be empty.")
    return tuple(result)


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _sort_evidence(snapshots: tuple[TradingViewEvidenceSnapshot, ...]) -> tuple[TradingViewEvidenceSnapshot, ...]:
    return tuple(sorted(snapshots, key=lambda item: _TIMEFRAME_PRIORITY.get(item.timeframe, 0)))


def _summary(
    snapshot: TradingViewEvidenceSnapshot,
    trigger_timestamp: datetime,
    maximum_source_age_seconds: int,
) -> TimeframeEvidenceSummary:
    completeness = EvidenceCompleteness.COMPLETE
    stale_evidence = snapshot.stale_evidence
    if (trigger_timestamp - snapshot.timestamp).total_seconds() > maximum_source_age_seconds:
        stale_evidence = tuple(dict.fromkeys((*stale_evidence, "tradingview_evidence")))
    if snapshot.invalid_evidence or stale_evidence or snapshot.missing_evidence:
        completeness = EvidenceCompleteness.PARTIAL
    return TimeframeEvidenceSummary(
        timeframe=snapshot.timeframe,
        direction=_direction(snapshot),
        completeness=completeness,
        missing_evidence=snapshot.missing_evidence,
        invalid_evidence=snapshot.invalid_evidence,
        stale_evidence=stale_evidence,
        timestamp=snapshot.timestamp,
        source_fingerprint=snapshot.source_fingerprint,
    )


def _direction(snapshot: TradingViewEvidenceSnapshot) -> FusionDirection:
    if (
        snapshot.market_context_status.availability is EvidenceAvailability.AVAILABLE
        and isinstance(snapshot.market_context_observation, MarketContextState)
    ):
        return _market_bias_direction(snapshot.market_context_observation.market_bias)
    if (
        snapshot.price_action_status.availability is EvidenceAvailability.AVAILABLE
        and isinstance(snapshot.price_action_observation, PriceActionState)
    ):
        return _trend_direction(snapshot.price_action_observation.trend)
    return FusionDirection.UNKNOWN


def _market_bias_direction(value: MarketBias) -> FusionDirection:
    if value is MarketBias.BULLISH:
        return FusionDirection.BULLISH
    if value is MarketBias.BEARISH:
        return FusionDirection.BEARISH
    if value is MarketBias.NEUTRAL:
        return FusionDirection.NEUTRAL
    if value is MarketBias.MIXED:
        return FusionDirection.MIXED
    return FusionDirection.UNKNOWN


def _trend_direction(value: Trend) -> FusionDirection:
    if value is Trend.BULLISH:
        return FusionDirection.BULLISH
    if value is Trend.BEARISH:
        return FusionDirection.BEARISH
    if value is Trend.RANGE:
        return FusionDirection.NEUTRAL
    return FusionDirection.UNKNOWN


def _alignment(
    directions: dict[str, FusionDirection],
) -> tuple[FusionDirection, tuple[str, ...], tuple[str, ...]]:
    if not directions:
        return FusionDirection.UNKNOWN, (), ()
    counts = Counter(directions.values())
    dominant_direction, dominant_count = sorted(
        counts.items(),
        key=lambda item: (item[1], _direction_priority(item[0])),
        reverse=True,
    )[0]
    aligned = tuple(timeframe for timeframe, direction in directions.items() if direction is dominant_direction)
    conflicting = tuple(timeframe for timeframe, direction in directions.items() if direction is not dominant_direction)
    if dominant_count == 1 and len(counts) > 1:
        return FusionDirection.UNKNOWN, (), tuple(directions)
    return dominant_direction, aligned, conflicting


def _direction_priority(direction: FusionDirection) -> int:
    return {
        FusionDirection.BULLISH: 3,
        FusionDirection.BEARISH: 2,
        FusionDirection.NEUTRAL: 1,
        FusionDirection.MIXED: 0,
        FusionDirection.UNKNOWN: 0,
    }.get(direction, 0)


def _completeness(
    summaries: tuple[TimeframeEvidenceSummary, ...],
    missing_timeframes: tuple[str, ...],
) -> EvidenceCompleteness:
    if not summaries:
        return EvidenceCompleteness.INSUFFICIENT
    if missing_timeframes or any(summary.completeness is not EvidenceCompleteness.COMPLETE for summary in summaries):
        return EvidenceCompleteness.PARTIAL
    return EvidenceCompleteness.COMPLETE


def _agreement(
    directions: dict[str, FusionDirection],
    aligned: tuple[str, ...],
    conflicting: tuple[str, ...],
    completeness: EvidenceCompleteness,
) -> EvidenceAgreement:
    if completeness is EvidenceCompleteness.INSUFFICIENT or not directions:
        return EvidenceAgreement.INSUFFICIENT_EVIDENCE
    if not conflicting and completeness is EvidenceCompleteness.COMPLETE:
        return EvidenceAgreement.FULL_ALIGNMENT
    if not conflicting:
        return EvidenceAgreement.PARTIAL_ALIGNMENT
    if len(aligned) > len(conflicting):
        return EvidenceAgreement.PARTIAL_ALIGNMENT
    if len(aligned) == len(conflicting):
        return EvidenceAgreement.MIXED
    return EvidenceAgreement.CONFLICT


def _conflict(
    conflicting: tuple[str, ...],
    directions: dict[str, FusionDirection],
    completeness: EvidenceCompleteness,
) -> EvidenceConflict:
    if completeness is EvidenceCompleteness.INSUFFICIENT or not directions:
        return EvidenceConflict.INSUFFICIENT
    if not conflicting:
        return EvidenceConflict.NONE
    if len(conflicting) < len(directions) / 2:
        return EvidenceConflict.MINOR
    return EvidenceConflict.MAJOR


def _dominant_timeframe(
    aligned: tuple[str, ...],
    summaries: tuple[TimeframeEvidenceSummary, ...],
) -> str:
    if not aligned:
        return "NONE"
    available = {item.timeframe for item in summaries if item.timeframe in aligned}
    return sorted(available, key=lambda item: _TIMEFRAME_PRIORITY.get(item, 0), reverse=True)[0]
