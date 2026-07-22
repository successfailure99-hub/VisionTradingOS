"""
Volume Context Engine V1.
"""

from __future__ import annotations

from math import isfinite
from numbers import Real

from core import events
from core.base_engine import BaseEngine
from core.models.candle import Candle

from .enums import (
    VolumeDirection,
    VolumeExhaustionState,
    VolumeExpansionState,
    VolumeStrength,
)
from .models import (
    VolumeContextDiagnosticSnapshot,
    VolumeContextProfile,
    VolumeContextSnapshot,
)


VOLUME_PRECISION = 2


class VolumeContextEngine(BaseEngine):
    """
    Deterministic closed-candle volume context evidence engine.

    This engine consumes closed candles for one externally owned
    instrument/timeframe lane. It does not fetch market data, process raw ticks,
    calculate confidence, or generate trade decisions.
    """

    def __init__(
        self,
        event_bus,
        *,
        instrument: str,
        timeframe: str,
        profile: VolumeContextProfile | int | None = None,
    ):
        super().__init__(event_bus)
        self._instrument = _normalize_instrument(instrument)
        self._timeframe = _normalize_text(timeframe, "timeframe")
        if profile is None:
            self._profile = VolumeContextProfile()
        elif isinstance(profile, VolumeContextProfile):
            self._profile = profile
        else:
            self._profile = VolumeContextProfile(profile)
        self._candles: list[Candle] = []
        self._last_fingerprint: tuple | None = None
        self._last_snapshot: VolumeContextSnapshot | None = None
        self._calculation_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error: str | None = None

    @property
    def state(self) -> VolumeContextSnapshot | None:
        return self._last_snapshot

    @property
    def lookback(self) -> int:
        return self._profile.lookback

    @property
    def candle_count(self) -> int:
        return len(self._candles)

    def process(self, candle: Candle) -> VolumeContextSnapshot:
        return self.update(candle)

    def update(self, candle: Candle) -> VolumeContextSnapshot:
        try:
            self._validate_candle(candle)
            candidate = self._normalized_history(candle)
            required = self._profile.lookback + 1
            if len(candidate) < required:
                self._candles = candidate
                self._partial_count += 1
                self._last_error = "Insufficient candle history for volume context."
                self._event_bus.publish(events.VOLUME_CONTEXT_PARTIAL, self.snapshot())
                raise ValueError(self._last_error)
            fingerprint = _history_fingerprint(candidate, self._profile)
            if fingerprint == self._last_fingerprint and self._last_snapshot is not None:
                self._candles = candidate
                return self._last_snapshot

            snapshot = self._calculate(candidate)
        except (TypeError, ValueError):
            if self._last_error is None:
                self._last_error = "Volume context input is invalid."
                self._invalid_count += 1
                self._event_bus.publish(events.VOLUME_CONTEXT_INVALID, self.snapshot())
            raise
        except Exception:
            self._failed_count += 1
            self._last_error = "Volume context calculation failed."
            self._event_bus.publish(events.VOLUME_CONTEXT_FAILED, self.snapshot())
            raise

        self._candles = candidate
        self._last_fingerprint = fingerprint
        if self._last_snapshot is not None and snapshot == self._last_snapshot:
            self._last_error = None
            return self._last_snapshot

        self._last_snapshot = snapshot
        self._data = snapshot
        self._last_error = None
        self._calculation_count += 1
        self._event_bus.publish(events.VOLUME_CONTEXT_UPDATED, snapshot)
        self._event_bus.publish(events.VOLUME_CONTEXT_STATE_UPDATED, self.snapshot())
        return snapshot

    def snapshot(self) -> VolumeContextDiagnosticSnapshot:
        return VolumeContextDiagnosticSnapshot(
            enabled=True,
            lookback=self._profile.lookback,
            calculation_count=self._calculation_count,
            partial_count=self._partial_count,
            invalid_count=self._invalid_count,
            failed_count=self._failed_count,
            last_snapshot=self._last_snapshot,
            last_error=self._last_error,
        )

    def reset(self) -> VolumeContextDiagnosticSnapshot:
        super().clear()
        self._candles.clear()
        self._last_fingerprint = None
        self._last_snapshot = None
        self._calculation_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error = None
        self._event_bus.publish(events.VOLUME_CONTEXT_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def clear(self) -> None:
        self.reset()

    def _normalized_history(self, candle: Candle) -> list[Candle]:
        """
        Maintain append-only volume history.

        The only permitted rewrite is a same end-time correction, used when an
        incomplete candle is replaced by its finalized canonical candle.
        """
        if not self._candles:
            return [candle]
        latest = self._candles[-1]
        if candle == latest:
            return list(self._candles)
        if candle.end_time == latest.end_time:
            if len(self._candles) > 1 and candle.start_time < self._candles[-2].end_time:
                self._record_invalid("Overlapping volume candle received.")
                raise ValueError(self._last_error)
            return [*self._candles[:-1], candle]
        if candle.end_time < latest.end_time:
            self._record_invalid("Stale volume candle received.")
            raise ValueError(self._last_error)
        if candle.start_time < latest.end_time:
            self._record_invalid("Overlapping volume candle received.")
            raise ValueError(self._last_error)
        return [*self._candles, candle]

    def _calculate(self, candles: list[Candle]) -> VolumeContextSnapshot:
        lookback = self._profile.lookback
        current_volume = int(candles[-1].volume)
        reference_volumes = tuple(int(candle.volume) for candle in candles[-lookback - 1:-1])
        average_volume = sum(reference_volumes) / lookback
        if average_volume <= 0:
            self._record_invalid("Average volume must be greater than zero.")
            raise ValueError(self._last_error)
        relative_volume = current_volume / average_volume
        snapshot = VolumeContextSnapshot(
            trading_date=candles[-1].end_time.date(),
            instrument=self._instrument,
            timeframe=self._timeframe,
            lookback=lookback,
            average_volume=round(average_volume, VOLUME_PRECISION),
            current_volume=current_volume,
            relative_volume=round(relative_volume, VOLUME_PRECISION),
            volume_direction=_direction(current_volume, candles[-2].volume, self._profile),
            volume_strength=_strength(relative_volume, self._profile),
            volume_expansion_state=_expansion(relative_volume, self._profile),
            volume_exhaustion_state=_exhaustion(relative_volume, self._profile),
            timestamp=candles[-1].end_time,
        )
        return snapshot

    def _validate_candle(self, candle: Candle) -> None:
        if not isinstance(candle, Candle):
            self._record_invalid("Volume context requires Candle input.")
            raise TypeError(self._last_error)
        if candle.symbol.strip().upper() != self._instrument:
            self._record_invalid("Volume candle instrument does not match engine.")
            raise ValueError(self._last_error)
        if candle.timeframe.strip() != self._timeframe:
            self._record_invalid("Volume candle timeframe does not match engine.")
            raise ValueError(self._last_error)
        for field_name in ("open", "high", "low", "close"):
            value = getattr(candle, field_name)
            if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) or float(value) <= 0:
                self._record_invalid(f"Candle {field_name} must be greater than zero and finite.")
                raise ValueError(self._last_error)
        if isinstance(candle.volume, bool) or not isinstance(candle.volume, int) or candle.volume < 0:
            self._record_invalid("Candle volume must be a non-negative integer.")
            raise ValueError(self._last_error)
        if candle.high < candle.low:
            self._record_invalid("Candle high must be greater than or equal to low.")
            raise ValueError(self._last_error)
        if not candle.low <= candle.open <= candle.high:
            self._record_invalid("Candle open must be within low and high.")
            raise ValueError(self._last_error)
        if not candle.low <= candle.close <= candle.high:
            self._record_invalid("Candle close must be within low and high.")
            raise ValueError(self._last_error)

    def _record_invalid(self, message: str) -> None:
        self._invalid_count += 1
        self._last_error = message
        self._event_bus.publish(events.VOLUME_CONTEXT_INVALID, self.snapshot())


def _direction(
    current_volume: int,
    previous_volume: int,
    profile: VolumeContextProfile,
) -> VolumeDirection:
    if previous_volume <= 0:
        if current_volume <= 0:
            return VolumeDirection.STABLE
        return VolumeDirection.INCREASING
    change_pct = ((current_volume - previous_volume) / previous_volume) * 100
    if abs(change_pct) <= profile.stable_threshold_pct:
        return VolumeDirection.STABLE
    if change_pct > 0:
        return VolumeDirection.INCREASING
    return VolumeDirection.DECREASING


def _strength(relative_volume: float, profile: VolumeContextProfile) -> VolumeStrength:
    if relative_volume < profile.low_rvol_threshold:
        return VolumeStrength.LOW
    if relative_volume < profile.high_rvol_threshold:
        return VolumeStrength.NORMAL
    if relative_volume < profile.extreme_rvol_threshold:
        return VolumeStrength.HIGH
    return VolumeStrength.EXTREME


def _expansion(relative_volume: float, profile: VolumeContextProfile) -> VolumeExpansionState:
    if relative_volume < profile.low_rvol_threshold:
        return VolumeExpansionState.COMPRESSED
    if relative_volume < profile.high_rvol_threshold:
        return VolumeExpansionState.NORMAL
    if relative_volume < profile.extreme_rvol_threshold:
        return VolumeExpansionState.EXPANDING
    return VolumeExpansionState.CLIMACTIC


def _exhaustion(relative_volume: float, profile: VolumeContextProfile) -> VolumeExhaustionState:
    if relative_volume >= profile.extreme_rvol_threshold:
        return VolumeExhaustionState.EXHAUSTED
    return VolumeExhaustionState.NORMAL


def _history_fingerprint(candles: list[Candle], profile: VolumeContextProfile) -> tuple:
    return (
        profile.lookback,
        profile.stable_threshold_pct,
        profile.low_rvol_threshold,
        profile.high_rvol_threshold,
        profile.extreme_rvol_threshold,
        tuple(
            (
                candle.symbol,
                candle.timeframe,
                candle.start_time,
                candle.end_time,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
            )
            for candle in candles
        ),
    )


def _normalize_instrument(value: str) -> str:
    normalized = _normalize_text(value, "instrument").upper()
    if normalized not in {"NIFTY", "BANKNIFTY", "SENSEX"}:
        raise ValueError("unsupported instrument.")
    return normalized


def _normalize_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text.")
    return value.strip()
