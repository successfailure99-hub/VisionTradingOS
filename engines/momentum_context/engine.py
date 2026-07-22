"""
Momentum Context Engine V1.
"""

from __future__ import annotations

from math import isfinite
from numbers import Real

from core import events
from core.base_engine import BaseEngine
from core.models.candle import Candle

from .enums import (
    MomentumAcceleration,
    MomentumDirection,
    MomentumState,
    MomentumStrength,
)
from .models import (
    MomentumContextDiagnosticSnapshot,
    MomentumContextProfile,
    MomentumContextSnapshot,
)


PRICE_PRECISION = 2
FLOAT_TOLERANCE = 1e-12


class MomentumContextEngine(BaseEngine):
    """
    Deterministic closed-candle momentum context evidence engine.

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
        profile: MomentumContextProfile | int | None = None,
    ):
        super().__init__(event_bus)
        self._instrument = _normalize_instrument(instrument)
        self._timeframe = _normalize_text(timeframe, "timeframe")
        if profile is None:
            self._profile = MomentumContextProfile()
        elif isinstance(profile, MomentumContextProfile):
            self._profile = profile
        else:
            self._profile = MomentumContextProfile(profile)
        self._candles: list[Candle] = []
        self._last_fingerprint: tuple | None = None
        self._last_snapshot: MomentumContextSnapshot | None = None
        self._calculation_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error: str | None = None

    @property
    def state(self) -> MomentumContextSnapshot | None:
        return self._last_snapshot

    @property
    def period(self) -> int:
        return self._profile.period

    @property
    def candle_count(self) -> int:
        return len(self._candles)

    def process(self, candle: Candle) -> MomentumContextSnapshot:
        return self.update(candle)

    def update(self, candle: Candle) -> MomentumContextSnapshot:
        try:
            self._validate_candle(candle)
            candidate = self._normalized_history(candle)
            required = self._profile.period + 1
            if len(candidate) < required:
                self._candles = candidate
                self._partial_count += 1
                self._last_error = "Insufficient candle history for momentum context."
                self._event_bus.publish(events.MOMENTUM_CONTEXT_PARTIAL, self.snapshot())
                raise ValueError(self._last_error)
            fingerprint = _history_fingerprint(candidate, self._profile)
            if fingerprint == self._last_fingerprint and self._last_snapshot is not None:
                self._candles = candidate
                return self._last_snapshot

            snapshot = self._calculate(candidate)
        except (TypeError, ValueError):
            if self._last_error is None:
                self._last_error = "Momentum context input is invalid."
                self._invalid_count += 1
                self._event_bus.publish(events.MOMENTUM_CONTEXT_INVALID, self.snapshot())
            raise
        except Exception:
            self._failed_count += 1
            self._last_error = "Momentum context calculation failed."
            self._event_bus.publish(events.MOMENTUM_CONTEXT_FAILED, self.snapshot())
            raise

        self._candles = candidate
        self._last_fingerprint = fingerprint
        self._last_snapshot = snapshot
        self._data = snapshot
        self._last_error = None
        self._calculation_count += 1
        self._event_bus.publish(events.MOMENTUM_CONTEXT_UPDATED, snapshot)
        self._event_bus.publish(events.MOMENTUM_CONTEXT_STATE_UPDATED, self.snapshot())
        return snapshot

    def snapshot(self) -> MomentumContextDiagnosticSnapshot:
        return MomentumContextDiagnosticSnapshot(
            enabled=True,
            period=self._profile.period,
            calculation_count=self._calculation_count,
            partial_count=self._partial_count,
            invalid_count=self._invalid_count,
            failed_count=self._failed_count,
            last_snapshot=self._last_snapshot,
            last_error=self._last_error,
        )

    def reset(self) -> MomentumContextDiagnosticSnapshot:
        super().clear()
        self._candles.clear()
        self._last_fingerprint = None
        self._last_snapshot = None
        self._calculation_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error = None
        self._event_bus.publish(events.MOMENTUM_CONTEXT_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def clear(self) -> None:
        self.reset()

    def _normalized_history(self, candle: Candle) -> list[Candle]:
        """
        Maintain append-only momentum history.

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
                self._record_invalid("Overlapping momentum candle received.")
                raise ValueError(self._last_error)
            return [*self._candles[:-1], candle]
        if candle.end_time < latest.end_time:
            self._record_invalid("Stale momentum candle received.")
            raise ValueError(self._last_error)
        if candle.start_time < latest.end_time:
            self._record_invalid("Overlapping momentum candle received.")
            raise ValueError(self._last_error)
        return [*self._candles, candle]

    def _calculate(self, candles: list[Candle]) -> MomentumContextSnapshot:
        closes = tuple(float(candle.close) for candle in candles)
        period = self._profile.period
        momentum_value = closes[-1] - closes[-period - 1]
        previous_momentum = None
        if len(closes) >= period + 2:
            previous_momentum = closes[-2] - closes[-period - 2]
        snapshot = MomentumContextSnapshot(
            trading_date=candles[-1].end_time.date(),
            instrument=self._instrument,
            timeframe=self._timeframe,
            momentum_period=period,
            momentum_value=round(momentum_value, PRICE_PRECISION),
            momentum_direction=_direction(momentum_value, self._profile.flat_threshold),
            momentum_strength=_strength(momentum_value, closes[-period - 1], self._profile),
            momentum_acceleration=_acceleration(momentum_value, previous_momentum, self._profile.flat_threshold),
            momentum_state=_state(momentum_value, previous_momentum, self._profile.flat_threshold),
            timestamp=candles[-1].end_time,
        )
        return snapshot

    def _validate_candle(self, candle: Candle) -> None:
        if not isinstance(candle, Candle):
            self._record_invalid("Momentum context requires Candle input.")
            raise TypeError(self._last_error)
        if candle.symbol.strip().upper() != self._instrument:
            self._record_invalid("Momentum candle instrument does not match engine.")
            raise ValueError(self._last_error)
        if candle.timeframe.strip() != self._timeframe:
            self._record_invalid("Momentum candle timeframe does not match engine.")
            raise ValueError(self._last_error)
        for field_name in ("open", "high", "low", "close"):
            value = getattr(candle, field_name)
            if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) or float(value) <= 0:
                self._record_invalid(f"Candle {field_name} must be greater than zero and finite.")
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
        self._event_bus.publish(events.MOMENTUM_CONTEXT_INVALID, self.snapshot())


def _direction(momentum_value: float, flat_threshold: float) -> MomentumDirection:
    if abs(momentum_value) <= flat_threshold + FLOAT_TOLERANCE:
        return MomentumDirection.FLAT
    if momentum_value > 0:
        return MomentumDirection.RISING
    return MomentumDirection.FALLING


def _strength(
    momentum_value: float,
    reference_price: float,
    profile: MomentumContextProfile,
) -> MomentumStrength:
    if reference_price <= 0:
        return MomentumStrength.WEAK
    momentum_pct = abs(momentum_value / reference_price) * 100
    if momentum_pct <= profile.weak_threshold_pct:
        return MomentumStrength.WEAK
    if momentum_pct < profile.strong_threshold_pct:
        return MomentumStrength.NORMAL
    if momentum_pct < profile.extreme_threshold_pct:
        return MomentumStrength.STRONG
    return MomentumStrength.EXTREME


def _acceleration(
    momentum_value: float,
    previous_momentum: float | None,
    flat_threshold: float,
) -> MomentumAcceleration:
    if previous_momentum is None:
        return MomentumAcceleration.STABLE
    if abs(abs(momentum_value) - abs(previous_momentum)) <= flat_threshold + FLOAT_TOLERANCE:
        return MomentumAcceleration.STABLE
    if abs(momentum_value) > abs(previous_momentum):
        return MomentumAcceleration.ACCELERATING
    return MomentumAcceleration.DECELERATING


def _state(
    momentum_value: float,
    previous_momentum: float | None,
    flat_threshold: float,
) -> MomentumState:
    if previous_momentum is None:
        return MomentumState.STABLE
    current_direction = _direction(momentum_value, flat_threshold)
    previous_direction = _direction(previous_momentum, flat_threshold)
    if (
        current_direction is not MomentumDirection.FLAT
        and previous_direction is not MomentumDirection.FLAT
        and current_direction is not previous_direction
    ):
        return MomentumState.REVERSING
    acceleration = _acceleration(momentum_value, previous_momentum, flat_threshold)
    if acceleration is MomentumAcceleration.ACCELERATING:
        return MomentumState.ACCELERATING
    if acceleration is MomentumAcceleration.DECELERATING:
        return MomentumState.DECELERATING
    return MomentumState.STABLE


def _history_fingerprint(candles: list[Candle], profile: MomentumContextProfile) -> tuple:
    return (
        profile.period,
        profile.flat_threshold,
        profile.weak_threshold_pct,
        profile.strong_threshold_pct,
        profile.extreme_threshold_pct,
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
