"""
Zerodha historical candle normalizer.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo

from brokers.zerodha.historical.intervals import interval_duration
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle


class ZerodhaHistoricalCandleNormalizer:
    def __init__(
        self,
        *,
        market_timezone: str = "Asia/Kolkata",
    ):
        self._timezone = ZoneInfo(market_timezone)

    def normalize(
        self,
        raw_candle: Mapping[str, object],
        *,
        instrument: Instrument,
        timeframe: TimeFrame,
    ) -> Candle:
        if not isinstance(raw_candle, Mapping):
            raise TypeError("raw_candle must be a mapping")
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be Instrument")
        if not isinstance(timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame")
        start = self._timestamp(raw_candle.get("date"))
        open_price = _positive_price(raw_candle.get("open"), "open")
        high = _positive_price(raw_candle.get("high"), "high")
        low = _positive_price(raw_candle.get("low"), "low")
        close = _positive_price(raw_candle.get("close"), "close")
        volume = _volume(raw_candle.get("volume"))
        if high < max(open_price, close, low):
            raise ValueError("candle high must be at or above open, close and low")
        if low > min(open_price, close, high):
            raise ValueError("candle low must be at or below open, close and high")
        if not (low <= open_price <= high):
            raise ValueError("candle open must be within high and low")
        if not (low <= close <= high):
            raise ValueError("candle close must be within high and low")
        return Candle(
            symbol=instrument.value,
            timeframe=timeframe.value,
            start_time=start,
            end_time=start + interval_duration(timeframe),
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )

    def normalize_many(
        self,
        raw_candles: Iterable[Mapping[str, object]],
        *,
        instrument: Instrument,
        timeframe: TimeFrame,
    ) -> tuple[Candle, ...]:
        if isinstance(raw_candles, (str, bytes, Mapping)):
            raise TypeError("raw_candles must be an iterable of mappings")
        return tuple(self.normalize(raw, instrument=instrument, timeframe=timeframe) for raw in raw_candles)

    def _timestamp(self, value: object) -> datetime:
        if value is None:
            raise ValueError("historical candle date is required")
        if isinstance(value, datetime):
            timestamp = value
        elif isinstance(value, str):
            try:
                timestamp = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("historical candle date must be ISO datetime") from exc
        else:
            raise TypeError("historical candle date must be datetime or ISO datetime string")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return timestamp.replace(tzinfo=self._timezone)
        return timestamp


def _number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _positive_price(value: object, field_name: str) -> float:
    normalized = _number(value, field_name)
    if normalized <= 0:
        raise ValueError(f"{field_name} must be positive")
    return normalized


def _volume(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("volume must be integer")
    if value < 0:
        raise ValueError("volume must be non-negative")
    return value
