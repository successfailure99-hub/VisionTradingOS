"""
Moving Average Context Engine V1.
"""

from __future__ import annotations

from math import isfinite
from numbers import Real

from core import events
from core.base_engine import BaseEngine
from core.models.candle import Candle

from .enums import (
    MovingAverageAlignment,
    MovingAverageCompressionState,
    MovingAverageExpansionState,
    MovingAverageSlope,
)
from .models import (
    MovingAverageContextDiagnosticSnapshot,
    MovingAverageContextProfile,
    MovingAverageContextSnapshot,
    MovingAverageValue,
)


PRICE_PRECISION = 2
SLOPE_TOLERANCE = 0.01
COMPRESSION_THRESHOLD_PCT = 0.25


class MovingAverageContextEngine(BaseEngine):
    """
    Deterministic EMA context evidence engine.

    This engine consumes closed candles for one externally owned
    instrument/timeframe lane. It does not fetch market data, process raw ticks,
    or own any runtime outside EMA context evidence.
    """

    def __init__(
        self,
        event_bus,
        *,
        instrument: str,
        timeframe: str,
        profile: MovingAverageContextProfile | tuple[int, ...] | None = None,
    ):
        super().__init__(event_bus)
        self._instrument = _normalize_instrument(instrument)
        self._timeframe = _normalize_text(timeframe, "timeframe")
        if profile is None:
            self._profile = MovingAverageContextProfile()
        elif isinstance(profile, MovingAverageContextProfile):
            self._profile = profile
        else:
            self._profile = MovingAverageContextProfile(tuple(profile))
        self._candles: list[Candle] = []
        self._last_fingerprint: tuple | None = None
        self._last_snapshot: MovingAverageContextSnapshot | None = None
        self._calculation_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error: str | None = None

    @property
    def state(self) -> MovingAverageContextSnapshot | None:
        return self._last_snapshot

    @property
    def periods(self) -> tuple[int, ...]:
        return self._profile.periods

    @property
    def candle_count(self) -> int:
        return len(self._candles)

    def process(self, candle: Candle) -> MovingAverageContextSnapshot:
        return self.update(candle)

    def update(self, candle: Candle) -> MovingAverageContextSnapshot:
        try:
            self._validate_candle(candle)
            candidate = self._normalized_history(candle)
            required = max(self._profile.periods)
            if len(candidate) < required:
                self._candles = candidate
                self._partial_count += 1
                self._last_error = "Insufficient candle history for moving average context."
                self._event_bus.publish(events.MA_CONTEXT_PARTIAL, self.snapshot())
                raise ValueError(self._last_error)
            fingerprint = _history_fingerprint(candidate, self._profile.periods)
            if fingerprint == self._last_fingerprint and self._last_snapshot is not None:
                self._candles = candidate
                return self._last_snapshot

            snapshot = self._calculate(candidate)
        except (TypeError, ValueError):
            if self._last_error is None:
                self._last_error = "Moving average context input is invalid."
                self._invalid_count += 1
                self._event_bus.publish(events.MA_CONTEXT_INVALID, self.snapshot())
            raise
        except Exception:
            self._failed_count += 1
            self._last_error = "Moving average context calculation failed."
            self._event_bus.publish(events.MA_CONTEXT_FAILED, self.snapshot())
            raise

        self._candles = candidate
        self._last_fingerprint = fingerprint
        self._last_snapshot = snapshot
        self._data = snapshot
        self._last_error = None
        self._calculation_count += 1
        self._event_bus.publish(events.MA_CONTEXT_UPDATED, snapshot)
        self._event_bus.publish(events.MA_CONTEXT_STATE_UPDATED, self.snapshot())
        return snapshot

    def snapshot(self) -> MovingAverageContextDiagnosticSnapshot:
        return MovingAverageContextDiagnosticSnapshot(
            enabled=True,
            periods=self._profile.periods,
            calculation_count=self._calculation_count,
            partial_count=self._partial_count,
            invalid_count=self._invalid_count,
            failed_count=self._failed_count,
            last_snapshot=self._last_snapshot,
            last_error=self._last_error,
        )

    def reset(self) -> MovingAverageContextDiagnosticSnapshot:
        super().clear()
        self._candles.clear()
        self._last_fingerprint = None
        self._last_snapshot = None
        self._calculation_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error = None
        self._event_bus.publish(events.MA_CONTEXT_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def clear(self) -> None:
        self.reset()

    def _normalized_history(self, candle: Candle) -> list[Candle]:
        if not self._candles:
            return [candle]
        latest = self._candles[-1]
        if candle == latest:
            return list(self._candles)
        if candle.end_time == latest.end_time:
            return [*self._candles[:-1], candle]
        if candle.end_time < latest.end_time:
            self._record_invalid("Stale moving average candle received.")
            raise ValueError(self._last_error)
        return [*self._candles, candle]

    def _calculate(self, candles: list[Candle]) -> MovingAverageContextSnapshot:
        closes = tuple(float(candle.close) for candle in candles)
        ema_series_by_period = {
            period: _ema_series(closes, period)
            for period in self._profile.periods
        }
        ema_values = tuple(
            MovingAverageValue(f"EMA{period}", period, round(ema_series_by_period[period][-1], PRICE_PRECISION))
            for period in self._profile.periods
        )
        ema_by_period = {item.period: item.value for item in ema_values}
        latest_close = closes[-1]
        ema20 = ema_by_period[20]
        ema50 = ema_by_period[50]
        ema200 = ema_by_period[200]
        previous = _previous_emas(ema_series_by_period)
        snapshot = MovingAverageContextSnapshot(
            trading_date=candles[-1].end_time.date(),
            instrument=self._instrument,
            timeframe=self._timeframe,
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            price_above_ema20=latest_close > ema20,
            price_above_ema50=latest_close > ema50,
            price_above_ema200=latest_close > ema200,
            ema_alignment=_alignment(latest_close, ema20, ema50, ema200),
            ema_slope=_slope(ema_series_by_period[20]),
            compression_state=_compression_state(latest_close, ema20, ema50, ema200, previous),
            expansion_state=_expansion_state(ema20, ema50, ema200, previous),
            timestamp=candles[-1].end_time,
            ema_values=ema_values,
        )
        return snapshot

    def _validate_candle(self, candle: Candle) -> None:
        if not isinstance(candle, Candle):
            self._record_invalid("Moving average context requires Candle input.")
            raise TypeError(self._last_error)
        if candle.symbol.strip().upper() != self._instrument:
            self._record_invalid("Moving average candle instrument does not match engine.")
            raise ValueError(self._last_error)
        if candle.timeframe.strip() != self._timeframe:
            self._record_invalid("Moving average candle timeframe does not match engine.")
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
        self._event_bus.publish(events.MA_CONTEXT_INVALID, self.snapshot())


def _ema_series(values: tuple[float, ...], period: int) -> tuple[float, ...]:
    if len(values) < period:
        return ()
    multiplier = 2 / (period + 1)
    ema = sum(values[:period]) / period
    result = [ema]
    for value in values[period:]:
        ema = ((value - ema) * multiplier) + ema
        result.append(ema)
    return tuple(result)


def _previous_emas(series_by_period: dict[int, tuple[float, ...]]) -> dict[int, float] | None:
    if any(len(values) < 2 for values in series_by_period.values()):
        return None
    return {period: values[-2] for period, values in series_by_period.items()}


def _alignment(price: float, ema20: float, ema50: float, ema200: float) -> MovingAverageAlignment:
    if price > ema20 > ema50 > ema200:
        return MovingAverageAlignment.STRONG_BULLISH
    if ema20 > ema50 > ema200:
        return MovingAverageAlignment.BULLISH
    if price < ema20 < ema50 < ema200:
        return MovingAverageAlignment.STRONG_BEARISH
    if ema20 < ema50 < ema200:
        return MovingAverageAlignment.BEARISH
    return MovingAverageAlignment.NEUTRAL


def _slope(ema20_series: tuple[float, ...]) -> MovingAverageSlope:
    if len(ema20_series) < 2:
        return MovingAverageSlope.FLAT
    current_delta = ema20_series[-1] - ema20_series[-2]
    if abs(current_delta) <= SLOPE_TOLERANCE:
        return MovingAverageSlope.FLAT
    if len(ema20_series) >= 3:
        previous_delta = ema20_series[-2] - ema20_series[-3]
        if abs(current_delta) > abs(previous_delta) + SLOPE_TOLERANCE:
            return MovingAverageSlope.ACCELERATING
        if abs(current_delta) < abs(previous_delta) - SLOPE_TOLERANCE:
            return MovingAverageSlope.DECELERATING
    if current_delta > 0:
        return MovingAverageSlope.RISING
    return MovingAverageSlope.FALLING


def _compression_state(
    price: float,
    ema20: float,
    ema50: float,
    ema200: float,
    previous: dict[int, float] | None,
) -> MovingAverageCompressionState:
    spread = max(ema20, ema50, ema200) - min(ema20, ema50, ema200)
    spread_pct = (spread / price) * 100
    if spread_pct <= COMPRESSION_THRESHOLD_PCT:
        return MovingAverageCompressionState.COMPRESSED
    if previous is not None:
        previous_spread = max(previous[20], previous[50], previous[200]) - min(previous[20], previous[50], previous[200])
        if spread > previous_spread + SLOPE_TOLERANCE:
            return MovingAverageCompressionState.EXPANDING
    return MovingAverageCompressionState.NORMAL


def _expansion_state(
    ema20: float,
    ema50: float,
    ema200: float,
    previous: dict[int, float] | None,
) -> MovingAverageExpansionState:
    if previous is None:
        return MovingAverageExpansionState.NORMAL
    spread = max(ema20, ema50, ema200) - min(ema20, ema50, ema200)
    previous_spread = max(previous[20], previous[50], previous[200]) - min(previous[20], previous[50], previous[200])
    if spread > previous_spread + SLOPE_TOLERANCE:
        return MovingAverageExpansionState.EXPANDING
    if spread < previous_spread - SLOPE_TOLERANCE:
        return MovingAverageExpansionState.COMPRESSED
    return MovingAverageExpansionState.NORMAL


def _history_fingerprint(candles: list[Candle], periods: tuple[int, ...]) -> tuple:
    return (
        periods,
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
