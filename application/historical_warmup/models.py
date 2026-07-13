"""
Immutable historical warm-up models.
"""

from dataclasses import dataclass
from datetime import datetime

from application.historical_warmup.enums import HistoricalWarmupOperation, HistoricalWarmupStatus
from application.models import RuntimeSnapshot
from brokers.zerodha.historical import ZerodhaHistoricalResult
from brokers.zerodha.instruments import ZerodhaInstrumentResolution
from core.enums.instrument import Instrument
from core.models.daily_ohlc import DailyOHLC


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
class HistoricalSeedResult:
    instrument: Instrument
    requested_count: int
    accepted_count: int
    duplicate_count: int
    rejected_count: int
    first_candle_at: datetime | None
    last_candle_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be Instrument")
        for name in ("requested_count", "accepted_count", "duplicate_count", "rejected_count"):
            _non_negative(getattr(self, name), name)
        if self.accepted_count + self.duplicate_count + self.rejected_count != self.requested_count:
            raise ValueError("accepted + duplicate + rejected must equal requested")
        _aware(self.first_candle_at, "first_candle_at")
        _aware(self.last_candle_at, "last_candle_at")


@dataclass(frozen=True, slots=True)
class HistoricalWarmupRequest:
    resolution: ZerodhaInstrumentResolution
    start_at: datetime
    end_at: datetime
    operation: HistoricalWarmupOperation

    def __post_init__(self) -> None:
        if not isinstance(self.resolution, ZerodhaInstrumentResolution):
            raise TypeError("resolution must be ZerodhaInstrumentResolution")
        object.__setattr__(self, "start_at", _aware(self.start_at, "start_at"))
        object.__setattr__(self, "end_at", _aware(self.end_at, "end_at"))
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be before end_at")
        if not isinstance(self.operation, HistoricalWarmupOperation):
            raise TypeError("operation must be HistoricalWarmupOperation")


@dataclass(frozen=True, slots=True)
class HistoricalWarmupInstrumentResult:
    instrument: Instrument
    historical_result: ZerodhaHistoricalResult
    seed_result: HistoricalSeedResult
    daily_ohlc: DailyOHLC | None
    runtime_snapshot: RuntimeSnapshot
    gaps_detected: int
    completed: bool
    error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be Instrument")
        if not isinstance(self.historical_result, ZerodhaHistoricalResult):
            raise TypeError("historical_result must be ZerodhaHistoricalResult")
        if not isinstance(self.seed_result, HistoricalSeedResult):
            raise TypeError("seed_result must be HistoricalSeedResult")
        if self.historical_result.request.instrument is not self.instrument:
            raise ValueError("historical result instrument does not match")
        if self.seed_result.instrument is not self.instrument:
            raise ValueError("seed result instrument does not match")
        if self.daily_ohlc is not None and not isinstance(self.daily_ohlc, DailyOHLC):
            raise TypeError("daily_ohlc must be DailyOHLC or None")
        if not isinstance(self.runtime_snapshot, RuntimeSnapshot):
            raise TypeError("runtime_snapshot must be RuntimeSnapshot")
        _non_negative(self.gaps_detected, "gaps_detected")
        if not isinstance(self.completed, bool):
            raise TypeError("completed must be bool")
        if self.completed and self.error is not None:
            raise ValueError("completed result cannot include error")
        if not self.completed and not self.error:
            raise ValueError("incomplete result requires error")


@dataclass(frozen=True, slots=True)
class HistoricalWarmupSnapshot:
    status: HistoricalWarmupStatus
    operation: HistoricalWarmupOperation | None
    configured_instruments: tuple[Instrument, ...]
    completed_instruments: tuple[Instrument, ...]
    failed_instruments: tuple[Instrument, ...]
    results: tuple[HistoricalWarmupInstrumentResult, ...]
    operation_count: int
    successful_operation_count: int
    failed_operation_count: int
    total_fetched_candles: int
    total_seeded_candles: int
    started_at: datetime | None
    completed_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, HistoricalWarmupStatus):
            raise TypeError("status must be HistoricalWarmupStatus")
        if self.operation is not None and not isinstance(self.operation, HistoricalWarmupOperation):
            raise TypeError("operation must be HistoricalWarmupOperation or None")
        for name in ("configured_instruments", "completed_instruments", "failed_instruments"):
            values = tuple(getattr(self, name))
            if any(not isinstance(value, Instrument) for value in values):
                raise TypeError(f"{name} must contain Instrument values")
            object.__setattr__(self, name, values)
        results = tuple(self.results)
        if any(not isinstance(result, HistoricalWarmupInstrumentResult) for result in results):
            raise TypeError("results must contain HistoricalWarmupInstrumentResult values")
        object.__setattr__(self, "results", results)
        if set(self.completed_instruments) & set(self.failed_instruments):
            raise ValueError("completed and failed instruments must be disjoint")
        for name in (
            "operation_count",
            "successful_operation_count",
            "failed_operation_count",
            "total_fetched_candles",
            "total_seeded_candles",
        ):
            _non_negative(getattr(self, name), name)
        _aware(self.started_at, "started_at")
        _aware(self.completed_at, "completed_at")
