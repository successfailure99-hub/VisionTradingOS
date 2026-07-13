"""
Immutable Zerodha historical data models.
"""

from dataclasses import dataclass
from datetime import datetime

from brokers.zerodha.historical.enums import HistoricalGapType, ZerodhaHistoricalStatus
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle


def _aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _non_negative(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ZerodhaHistoricalRequest:
    instrument_token: int
    instrument: Instrument
    exchange: Exchange
    timeframe: TimeFrame
    start_at: datetime
    end_at: datetime
    continuous: bool = False
    include_open_interest: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.instrument_token, bool) or not isinstance(self.instrument_token, int) or self.instrument_token <= 0:
            raise ValueError("instrument_token must be a positive integer")
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be Instrument")
        if not isinstance(self.exchange, Exchange):
            raise TypeError("exchange must be Exchange")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame")
        object.__setattr__(self, "start_at", _aware(self.start_at, "start_at"))
        object.__setattr__(self, "end_at", _aware(self.end_at, "end_at"))
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be before end_at")
        if not isinstance(self.continuous, bool):
            raise TypeError("continuous must be bool")
        if not isinstance(self.include_open_interest, bool):
            raise TypeError("include_open_interest must be bool")
        if self.instrument.is_index and (self.continuous or self.include_open_interest):
            raise ValueError("index historical requests must not use continuous or open interest")


@dataclass(frozen=True, slots=True)
class ZerodhaHistoricalChunk:
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_at", _aware(self.start_at, "start_at"))
        object.__setattr__(self, "end_at", _aware(self.end_at, "end_at"))
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be before end_at")


@dataclass(frozen=True, slots=True)
class HistoricalGap:
    gap_type: HistoricalGapType
    expected_at: datetime | None
    previous_at: datetime | None
    next_at: datetime | None
    missing_intervals: int

    def __post_init__(self) -> None:
        if not isinstance(self.gap_type, HistoricalGapType):
            raise TypeError("gap_type must be HistoricalGapType")
        _aware(self.expected_at, "expected_at")
        _aware(self.previous_at, "previous_at")
        _aware(self.next_at, "next_at")
        _non_negative(self.missing_intervals, "missing_intervals")


@dataclass(frozen=True, slots=True)
class ZerodhaHistoricalResult:
    request: ZerodhaHistoricalRequest
    candles: tuple[Candle, ...]
    gaps: tuple[HistoricalGap, ...]
    source_record_count: int
    normalized_count: int
    duplicate_count: int
    rejected_count: int
    first_candle_at: datetime | None
    last_candle_at: datetime | None
    fetched_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.request, ZerodhaHistoricalRequest):
            raise TypeError("request must be ZerodhaHistoricalRequest")
        candles = tuple(self.candles)
        gaps = tuple(self.gaps)
        if any(not isinstance(candle, Candle) for candle in candles):
            raise TypeError("candles must contain Candle values")
        if any(not isinstance(gap, HistoricalGap) for gap in gaps):
            raise TypeError("gaps must contain HistoricalGap values")
        object.__setattr__(self, "candles", candles)
        object.__setattr__(self, "gaps", gaps)
        for name in ("source_record_count", "normalized_count", "duplicate_count", "rejected_count"):
            _non_negative(getattr(self, name), name)
        if self.normalized_count != len(candles):
            raise ValueError("normalized_count must equal candles length")
        expected_first = candles[0].start_time if candles else None
        expected_last = candles[-1].start_time if candles else None
        if self.first_candle_at != expected_first or self.last_candle_at != expected_last:
            raise ValueError("first/last candle timestamps must match candles")
        _aware(self.first_candle_at, "first_candle_at")
        _aware(self.last_candle_at, "last_candle_at")
        _aware(self.fetched_at, "fetched_at")


@dataclass(frozen=True, slots=True)
class ZerodhaHistoricalSnapshot:
    status: ZerodhaHistoricalStatus
    fetch_count: int
    successful_fetch_count: int
    failed_fetch_count: int
    total_source_records: int
    total_normalized_candles: int
    last_request: ZerodhaHistoricalRequest | None
    last_result: ZerodhaHistoricalResult | None
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ZerodhaHistoricalStatus):
            raise TypeError("status must be ZerodhaHistoricalStatus")
        for name in ("fetch_count", "successful_fetch_count", "failed_fetch_count", "total_source_records", "total_normalized_candles"):
            _non_negative(getattr(self, name), name)
        if self.last_request is not None and not isinstance(self.last_request, ZerodhaHistoricalRequest):
            raise TypeError("last_request must be ZerodhaHistoricalRequest or None")
        if self.last_result is not None and not isinstance(self.last_result, ZerodhaHistoricalResult):
            raise TypeError("last_result must be ZerodhaHistoricalResult or None")
        _aware(self.last_started_at, "last_started_at")
        _aware(self.last_completed_at, "last_completed_at")
