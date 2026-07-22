"""
ADR Engine V1.
"""

from __future__ import annotations

from datetime import date, datetime
from math import isfinite
from numbers import Real

from core.base_engine import BaseEngine
from core import events
from core.models.daily_ohlc import DailyOHLC

from .enums import ADRExpansionState, ADRExhaustionState
from .models import ADRDiagnosticSnapshot, ADRRequest, ADRSnapshot


SUPPORTED_ADR_PERIODS = (5, 10, 20, 50)
PRICE_PRECISION = 2
PERCENT_PRECISION = 2


class ADREngine(BaseEngine):
    """
    Deterministic Average Daily Range evidence engine.

    ADR Engine V1 consumes externally supplied daily OHLC history and the
    current session range. It does not fetch data, process ticks, generate
    strategy signals, or own market-data runtime behavior.
    """

    def __init__(self, event_bus, *, instrument: str, period: int = 20):
        super().__init__(event_bus)
        self._instrument = _normalize_instrument(instrument)
        self._period = _validate_period(period)
        self._last_request_fingerprint: tuple | None = None
        self._last_snapshot: ADRSnapshot | None = None
        self._calculation_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._last_error: str | None = None

    @property
    def period(self) -> int:
        return self._period

    @property
    def state(self) -> ADRSnapshot | None:
        return self._last_snapshot

    def calculate(self, request: ADRRequest) -> ADRSnapshot:
        if not isinstance(request, ADRRequest):
            self._invalid_count += 1
            self._last_error = "ADR request is invalid."
            self._event_bus.publish(events.ADR_INVALID, self.snapshot())
            raise TypeError("request must be ADRRequest.")
        if request.instrument != self._instrument:
            self._invalid_count += 1
            self._last_error = "ADR request instrument does not match engine."
            self._event_bus.publish(events.ADR_INVALID, self.snapshot())
            raise ValueError(self._last_error)

        history = self._validated_history(request.daily_history)
        if len(history) < self._period:
            self._partial_count += 1
            self._last_error = "Insufficient daily history for ADR."
            self._event_bus.publish(events.ADR_PARTIAL, self.snapshot())
            raise ValueError(self._last_error)

        selected = history[-self._period :]
        fingerprint = (
            request.trading_date,
            request.instrument,
            request.latest_price,
            request.session_high,
            request.session_low,
            request.timestamp,
            tuple((item.trading_date, item.high, item.low) for item in selected),
        )
        if fingerprint == self._last_request_fingerprint and self._last_snapshot is not None:
            return self._last_snapshot

        adr_value = round(sum(item.high - item.low for item in selected) / self._period, PRICE_PRECISION)
        today_range = round(request.session_high - request.session_low, PRICE_PRECISION)
        consumed = round((today_range / adr_value) * 100, PERCENT_PRECISION)
        remaining = round(max(0.0, 100.0 - consumed), PERCENT_PRECISION)
        expansion = _expansion_state(consumed, today_range)
        exhaustion = _exhaustion_state(consumed, today_range)
        snapshot = ADRSnapshot(
            trading_date=request.trading_date,
            instrument=request.instrument,
            adr_period=self._period,
            adr_value=adr_value,
            today_high=round(request.session_high, PRICE_PRECISION),
            today_low=round(request.session_low, PRICE_PRECISION),
            today_range=today_range,
            adr_high=round(request.session_low + adr_value, PRICE_PRECISION),
            adr_low=round(request.session_high - adr_value, PRICE_PRECISION),
            range_consumed_pct=consumed,
            range_remaining_pct=remaining,
            expansion_state=expansion,
            exhaustion_state=exhaustion,
            timestamp=request.timestamp,
        )
        self._last_request_fingerprint = fingerprint
        self._last_snapshot = snapshot
        self._data = snapshot
        self._last_error = None
        self._calculation_count += 1
        self._event_bus.publish(events.ADR_UPDATED, snapshot)
        self._event_bus.publish(events.ADR_STATE_UPDATED, self.snapshot())
        return snapshot

    def update(
        self,
        *,
        trading_date: date,
        daily_history: tuple[DailyOHLC, ...],
        latest_price: float,
        session_high: float,
        session_low: float,
        timestamp: datetime,
    ) -> ADRSnapshot:
        return self.calculate(
            ADRRequest(
                trading_date=trading_date,
                instrument=self._instrument,
                daily_history=daily_history,
                latest_price=latest_price,
                session_high=session_high,
                session_low=session_low,
                timestamp=timestamp,
            )
        )

    def snapshot(self) -> ADRDiagnosticSnapshot:
        return ADRDiagnosticSnapshot(
            enabled=True,
            period=self._period,
            calculation_count=self._calculation_count,
            partial_count=self._partial_count,
            invalid_count=self._invalid_count,
            last_snapshot=self._last_snapshot,
            last_error=self._last_error,
        )

    def reset(self) -> ADRDiagnosticSnapshot:
        super().clear()
        self._last_request_fingerprint = None
        self._last_snapshot = None
        self._calculation_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._last_error = None
        self._event_bus.publish(events.ADR_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def clear(self) -> None:
        self.reset()

    def _validated_history(self, values: tuple[object, ...]) -> tuple[DailyOHLC, ...]:
        if not values:
            return ()
        normalized = []
        seen_dates = set()
        for item in values:
            if not isinstance(item, DailyOHLC):
                self._invalid_count += 1
                self._last_error = "ADR daily history must contain DailyOHLC values."
                self._event_bus.publish(events.ADR_INVALID, self.snapshot())
                raise TypeError(self._last_error)
            _validate_daily_ohlc(item)
            if item.trading_date in seen_dates:
                self._invalid_count += 1
                self._last_error = "ADR daily history contains duplicate trading dates."
                self._event_bus.publish(events.ADR_INVALID, self.snapshot())
                raise ValueError(self._last_error)
            seen_dates.add(item.trading_date)
            normalized.append(item)
        return tuple(sorted(normalized, key=lambda item: item.trading_date))


def _normalize_instrument(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("instrument must be non-empty text.")
    normalized = value.strip().upper()
    if normalized not in {"NIFTY", "BANKNIFTY", "SENSEX"}:
        raise ValueError("unsupported instrument.")
    return normalized


def _validate_period(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in SUPPORTED_ADR_PERIODS:
        raise ValueError("ADR period must be one of 5, 10, 20 or 50.")
    return value


def _validate_daily_ohlc(item: DailyOHLC) -> None:
    if not isinstance(item.trading_date, date) or isinstance(item.trading_date, datetime):
        raise ValueError("DailyOHLC trading_date must be a date.")
    for field_name in ("open", "high", "low", "close"):
        value = getattr(item, field_name)
        if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) or float(value) <= 0:
            raise ValueError(f"DailyOHLC {field_name} must be greater than zero and finite.")
    if item.high <= item.low:
        raise ValueError("DailyOHLC high must be greater than low.")
    if not item.low <= item.open <= item.high:
        raise ValueError("DailyOHLC open must be within low and high.")
    if not item.low <= item.close <= item.high:
        raise ValueError("DailyOHLC close must be within low and high.")


def _expansion_state(consumed: float, today_range: float) -> ADRExpansionState:
    if today_range <= 0:
        return ADRExpansionState.NOT_STARTED
    if consumed < 75:
        return ADRExpansionState.NORMAL
    if consumed < 100:
        return ADRExpansionState.EXPANDING
    if abs(consumed - 100.0) <= 1e-9:
        return ADRExpansionState.ADR_REACHED
    if consumed <= 120:
        return ADRExpansionState.ADR_EXCEEDED
    return ADRExpansionState.EXTREME_EXPANSION


def _exhaustion_state(consumed: float, today_range: float) -> ADRExhaustionState:
    if today_range <= 0:
        return ADRExhaustionState.NOT_STARTED
    if consumed < 100:
        return ADRExhaustionState.NOT_EXHAUSTED
    if consumed <= 120:
        return ADRExhaustionState.EXHAUSTED
    return ADRExhaustionState.EXTREME

