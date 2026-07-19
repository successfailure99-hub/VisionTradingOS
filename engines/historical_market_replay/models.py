from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from application.enums import RuntimeInstrument
from brokers.zerodha.enums import BrokerExecutionMode
from application.enums import ExecutionSafetyMode
from core.models.tick import Tick
from engines.historical_market_replay.enums import ReplayLifecycleState, ReplayMode, ReplayOutcome, ReplayRecordType, ReplaySeverity
from engines.option_chain.models import OptionChainSnapshot


IST = ZoneInfo("Asia/Kolkata")
SUPPORTED_REPLAY_INSTRUMENTS = (RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.SENSEX)


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _non_negative_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _finite_positive(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
        raise ValueError(f"{name} must be finite and greater than zero")
    return float(value)


def _aware(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class ReplayConfiguration:
    enabled: bool = False
    mode: ReplayMode = ReplayMode.OFF
    source_path: Path | str | None = None
    speed_multiplier: float = 10.0
    auto_load: bool = False
    auto_start: bool = False
    output_dir: Path | str = Path("logs/historical_replay")
    max_findings: int = 500
    max_recent_identities: int = 2000
    max_latency_samples: int = 1000
    max_batch_records: int = 1
    safety_mode: ExecutionSafetyMode = ExecutionSafetyMode.ANALYSIS_ONLY
    broker_mode: BrokerExecutionMode = BrokerExecutionMode.DRY_RUN

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool")
        mode = self.mode if isinstance(self.mode, ReplayMode) else ReplayMode(str(self.mode).strip().lower())
        object.__setattr__(self, "mode", mode)
        source = None if self.source_path in (None, "") else Path(self.source_path)
        object.__setattr__(self, "source_path", source)
        object.__setattr__(self, "speed_multiplier", _finite_positive(self.speed_multiplier, "speed_multiplier"))
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        _positive_int(self.max_findings, "max_findings")
        _positive_int(self.max_recent_identities, "max_recent_identities")
        _positive_int(self.max_latency_samples, "max_latency_samples")
        _positive_int(self.max_batch_records, "max_batch_records")
        if self.broker_mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("historical replay requires DRY_RUN broker mode")
        if self.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
            raise ValueError("historical replay requires ANALYSIS_ONLY safety mode")
        if self.enabled and mode is ReplayMode.OFF:
            raise ValueError("enabled historical replay cannot use OFF mode")
        if self.auto_load and (not self.enabled or source is None):
            raise ValueError("historical replay AUTO_LOAD requires enabled replay and source path")
        if self.auto_start and (not self.enabled or mode is ReplayMode.OFF or source is None):
            raise ValueError("historical replay AUTO_START requires enabled replay, non-OFF mode and source path")
        if self.auto_start and not self.auto_load:
            raise ValueError("historical replay AUTO_START requires AUTO_LOAD")


@dataclass(frozen=True, slots=True)
class ReplayManifest:
    session_id: str
    trading_date: date
    timezone: str
    instruments: tuple[RuntimeInstrument, ...]
    created_at: datetime
    record_count: int
    source: str

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id must be non-empty")
        _aware(self.created_at, "created_at")
        _non_negative_int(self.record_count, "record_count")
        instruments = tuple(self.instruments)
        if not instruments:
            raise ValueError("manifest instruments cannot be empty")
        for instrument in instruments:
            if instrument not in SUPPORTED_REPLAY_INSTRUMENTS:
                raise ValueError("historical replay supports only NIFTY, BANKNIFTY and SENSEX")
        object.__setattr__(self, "instruments", instruments)


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    sequence: int
    record_type: ReplayRecordType
    event_timestamp: datetime
    instrument: RuntimeInstrument
    payload: Tick | OptionChainSnapshot

    def __post_init__(self) -> None:
        _non_negative_int(self.sequence, "sequence")
        _aware(self.event_timestamp, "event_timestamp")
        if not isinstance(self.record_type, ReplayRecordType):
            raise TypeError("record_type must be ReplayRecordType")
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")


@dataclass(frozen=True, slots=True)
class ReplayCounters:
    published_records: int = 0
    tick_publications: int = 0
    option_chain_publications: int = 0
    skipped_records: int = 0
    duplicate_count: int = 0
    out_of_order_count: int = 0
    invalid_record_count: int = 0
    broker_order_calls: int = 0
    persistence_writes: int = 0
    persistence_failures: int = 0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _non_negative_int(getattr(self, name), name)
        if self.broker_order_calls != 0:
            raise ValueError("broker_order_calls must remain zero")


@dataclass(frozen=True, slots=True)
class ReplayFinding:
    finding_id: str
    timestamp: datetime
    severity: ReplaySeverity
    code: str
    message: str
    observed_value: str | None = None
    occurrence_count: int = 1
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None

    def __post_init__(self) -> None:
        _aware(self.timestamp, "timestamp")
        if not self.finding_id.strip() or not self.code.strip() or not self.message.strip():
            raise ValueError("finding fields must be non-empty")
        _positive_int(self.occurrence_count, "occurrence_count")
        object.__setattr__(self, "first_seen_at", self.first_seen_at or self.timestamp)
        object.__setattr__(self, "last_seen_at", self.last_seen_at or self.timestamp)

    def aggregate(self, timestamp: datetime, observed_value: str | None = None) -> "ReplayFinding":
        return ReplayFinding(
            finding_id=self.finding_id,
            timestamp=self.timestamp,
            severity=self.severity,
            code=self.code,
            message=self.message,
            observed_value=observed_value if observed_value is not None else self.observed_value,
            occurrence_count=self.occurrence_count + 1,
            first_seen_at=self.first_seen_at,
            last_seen_at=timestamp,
        )


@dataclass(frozen=True, slots=True)
class ReplayLatencySummary:
    count: int = 0
    latest_ms: float = 0.0
    maximum_ms: float = 0.0
    average_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class ReplaySessionSnapshot:
    session_id: str
    lifecycle_state: ReplayLifecycleState
    mode: ReplayMode
    instruments: tuple[RuntimeInstrument, ...]
    source_path: Path | None
    trading_date: date | None
    total_records: int
    current_record_index: int
    current_sequence: int | None
    first_event_timestamp: datetime | None
    current_event_timestamp: datetime | None
    last_published_event_timestamp: datetime | None
    speed_multiplier: float
    started_at: datetime | None
    paused_at: datetime | None
    ended_at: datetime | None
    failure_reason: str | None
    active_findings: tuple[ReplayFinding, ...]
    counters: ReplayCounters
    latency_summary: ReplayLatencySummary
    final_outcome: ReplayOutcome | None
    final_summary: str = "-"

    @property
    def published_records(self) -> int:
        return self.counters.published_records

    @property
    def remaining_records(self) -> int:
        return max(self.total_records - self.current_record_index, 0)

    @property
    def progress_percentage(self) -> float:
        return 0.0 if self.total_records <= 0 else min((self.current_record_index / self.total_records) * 100.0, 100.0)


@dataclass(frozen=True, slots=True)
class ReplayReport:
    session_id: str
    manifest: ReplayManifest | None
    snapshot: ReplaySessionSnapshot
    outcome: ReplayOutcome
    created_at: datetime
    report_path: Path | None = None
