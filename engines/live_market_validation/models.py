from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from application.enums import ExecutionSafetyMode, RuntimeInstrument
from brokers.zerodha.enums import BrokerExecutionMode
from engines.live_market_validation.enums import (
    ComponentStatus,
    FindingResolution,
    OptionSnapshotQuality,
    RecoveryState,
    ValidationComponent,
    ValidationHealth,
    ValidationLifecycleState,
    ValidationMode,
    ValidationOutcome,
    ValidationSeverity,
)


IST = ZoneInfo("Asia/Kolkata")
SUPPORTED_VALIDATION_INSTRUMENTS = (
    RuntimeInstrument.NIFTY,
    RuntimeInstrument.BANKNIFTY,
    RuntimeInstrument.SENSEX,
)


def _require_aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _finite(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{field_name} must be finite")
    return float(value)


@dataclass(frozen=True, slots=True)
class LiveMarketValidationConfiguration:
    enabled: bool = False
    mode: ValidationMode = ValidationMode.OFF
    instruments: tuple[RuntimeInstrument, ...] = SUPPORTED_VALIDATION_INSTRUMENTS
    output_dir: Path | str = Path("logs/live_validation")
    tick_stale_after_seconds: int = 10
    tick_gap_warning_seconds: int = 30
    tick_gap_critical_seconds: int = 60
    option_chain_stale_seconds: int = 60
    component_stale_seconds: int = 120
    event_latency_warning_ms: int = 500
    event_latency_critical_ms: int = 1500
    max_recent_identities: int = 256
    max_findings: int = 512
    max_latency_samples: int = 512
    max_reconnect_history: int = 64
    required_components: tuple[ValidationComponent, ...] = (
        ValidationComponent.MARKET_DATA,
        ValidationComponent.CANDLE,
        ValidationComponent.PRICE_ACTION,
        ValidationComponent.OPTION_CHAIN,
        ValidationComponent.PAPER_TRADING,
        ValidationComponent.PERFORMANCE_ANALYTICS,
    )
    session_start: time = time(9, 15)
    session_end: time = time(15, 30)
    safety_mode: ExecutionSafetyMode = ExecutionSafetyMode.ANALYSIS_ONLY
    broker_mode: BrokerExecutionMode = BrokerExecutionMode.DRY_RUN

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool")
        mode = self.mode if isinstance(self.mode, ValidationMode) else ValidationMode(str(self.mode).strip().lower())
        object.__setattr__(self, "mode", mode)
        instruments = tuple(self.instruments)
        if not instruments:
            raise ValueError("validation instruments cannot be empty")
        normalized = []
        for instrument in instruments:
            if not isinstance(instrument, RuntimeInstrument):
                instrument = RuntimeInstrument(str(instrument).strip().upper())
            if instrument not in SUPPORTED_VALIDATION_INSTRUMENTS:
                raise ValueError("validation supports only NIFTY, BANKNIFTY and SENSEX")
            if instrument not in normalized:
                normalized.append(instrument)
        object.__setattr__(self, "instruments", tuple(normalized))
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        for name in (
            "tick_stale_after_seconds",
            "tick_gap_warning_seconds",
            "tick_gap_critical_seconds",
            "option_chain_stale_seconds",
            "component_stale_seconds",
            "event_latency_warning_ms",
            "event_latency_critical_ms",
        ):
            _non_negative_int(getattr(self, name), name)
        for name in ("max_recent_identities", "max_findings", "max_latency_samples", "max_reconnect_history"):
            _positive_int(getattr(self, name), name)
        if self.tick_gap_critical_seconds < self.tick_gap_warning_seconds:
            raise ValueError("critical tick gap threshold cannot be below warning threshold")
        if self.event_latency_critical_ms < self.event_latency_warning_ms:
            raise ValueError("critical latency threshold cannot be below warning threshold")
        required = []
        for component in tuple(self.required_components):
            if not isinstance(component, ValidationComponent):
                component = ValidationComponent(str(component).strip().lower())
            if component not in required:
                required.append(component)
        object.__setattr__(self, "required_components", tuple(required))
        if not isinstance(self.session_start, time) or not isinstance(self.session_end, time):
            raise TypeError("session boundaries must be time values")
        if self.session_start >= self.session_end:
            raise ValueError("session_start must be before session_end")
        if self.broker_mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("live validation requires DRY_RUN broker mode")
        if self.safety_mode not in (ExecutionSafetyMode.ANALYSIS_ONLY, ExecutionSafetyMode.DRY_RUN):
            raise ValueError("live validation requires ANALYSIS_ONLY or DRY_RUN safety mode")
        if mode is ValidationMode.LIVE_OBSERVE and self.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
            raise ValueError("LIVE_OBSERVE requires ANALYSIS_ONLY safety mode")


@dataclass(frozen=True, slots=True)
class ValidationCounters:
    observed_events: int = 0
    duplicate_events: int = 0
    out_of_order_events: int = 0
    handler_failures: int = 0
    broker_order_calls: int = 0
    persistence_writes: int = 0
    persistence_failures: int = 0

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            _non_negative_int(getattr(self, field_name), field_name)
        if self.broker_order_calls != 0:
            raise ValueError("broker_order_calls must remain zero")


@dataclass(frozen=True, slots=True)
class TickValidationMetrics:
    received_ticks: int = 0
    valid_ticks: int = 0
    duplicate_ticks: int = 0
    out_of_order_ticks: int = 0
    stale_ticks: int = 0
    invalid_ticks: int = 0
    largest_gap_seconds: float = 0.0
    current_gap_seconds: float = 0.0
    last_tick_age_seconds: float = 0.0
    first_tick_timestamp: datetime | None = None
    latest_tick_timestamp: datetime | None = None
    last_price: float | None = None


@dataclass(frozen=True, slots=True)
class CandleValidationMetrics:
    updated_candles: int = 0
    closed_candles: int = 0
    duplicate_closed_candles: int = 0
    out_of_order_candles: int = 0
    missing_intervals: int = 0
    invalid_ohlc_candles: int = 0
    late_closes: int = 0


@dataclass(frozen=True, slots=True)
class OptionChainValidationMetrics:
    snapshots_received: int = 0
    complete_snapshots: int = 0
    partial_snapshots: int = 0
    stale_snapshots: int = 0
    invalid_snapshots: int = 0
    duplicate_snapshots: int = 0
    latest_snapshot_age_seconds: float = 0.0
    quality: OptionSnapshotQuality = OptionSnapshotQuality.UNAVAILABLE


@dataclass(frozen=True, slots=True)
class ComponentFreshness:
    component: ValidationComponent
    instrument: RuntimeInstrument | None
    latest_observed_at: datetime | None = None
    latest_source_at: datetime | None = None
    age_seconds: float | None = None
    status: ComponentStatus = ComponentStatus.NOT_OBSERVED
    observations: int = 0
    last_finding_id: str | None = None
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.component, ValidationComponent):
            raise TypeError("component must be ValidationComponent")
        if self.instrument is not None and not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument or None")
        for name in ("latest_observed_at", "latest_source_at"):
            value = getattr(self, name)
            if value is not None:
                _require_aware(value, name)
        if self.age_seconds is not None:
            _finite(self.age_seconds, "age_seconds")
        _non_negative_int(self.observations, "observations")
        object.__setattr__(self, "dependencies", tuple(str(item) for item in self.dependencies))


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    finding_id: str
    session_id: str
    timestamp: datetime
    severity: ValidationSeverity
    category: str
    component: ValidationComponent
    code: str
    message: str
    instrument: RuntimeInstrument | None = None
    observed_value: str | None = None
    expected_value: str | None = None
    source_event_identity: str | None = None
    occurrence_count: int = 1
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    resolution: FindingResolution = FindingResolution.ACTIVE

    def __post_init__(self) -> None:
        if not isinstance(self.finding_id, str) or not self.finding_id.strip():
            raise ValueError("finding_id must be non-empty")
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise ValueError("session_id must be non-empty")
        _require_aware(self.timestamp, "timestamp")
        if not isinstance(self.severity, ValidationSeverity):
            raise TypeError("severity must be ValidationSeverity")
        if not isinstance(self.component, ValidationComponent):
            raise TypeError("component must be ValidationComponent")
        if self.instrument is not None and not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument or None")
        for name in ("category", "code", "message"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty text")
        _positive_int(self.occurrence_count, "occurrence_count")
        object.__setattr__(self, "first_seen_at", self.first_seen_at or self.timestamp)
        object.__setattr__(self, "last_seen_at", self.last_seen_at or self.timestamp)

    def aggregate(self, timestamp: datetime, observed_value: str | None = None) -> "ValidationFinding":
        _require_aware(timestamp, "timestamp")
        return ValidationFinding(
            finding_id=self.finding_id,
            session_id=self.session_id,
            timestamp=self.timestamp,
            severity=self.severity,
            category=self.category,
            component=self.component,
            code=self.code,
            message=self.message,
            instrument=self.instrument,
            observed_value=observed_value if observed_value is not None else self.observed_value,
            expected_value=self.expected_value,
            source_event_identity=self.source_event_identity,
            occurrence_count=self.occurrence_count + 1,
            first_seen_at=self.first_seen_at,
            last_seen_at=timestamp,
            resolution=self.resolution,
        )


@dataclass(frozen=True, slots=True)
class LatencySummary:
    name: str
    count: int = 0
    latest_ms: float = 0.0
    minimum_ms: float = 0.0
    maximum_ms: float = 0.0
    average_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    bounded_samples: bool = True


@dataclass(frozen=True, slots=True)
class ReconnectSummary:
    recovery_state: RecoveryState = RecoveryState.CONNECTED
    disconnect_count: int = 0
    reconnect_count: int = 0
    total_outage_seconds: float = 0.0
    longest_outage_seconds: float = 0.0
    last_disconnect_at: datetime | None = None
    last_reconnect_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class InstrumentValidationSummary:
    instrument: RuntimeInstrument
    health: ValidationHealth
    tick_metrics: TickValidationMetrics = field(default_factory=TickValidationMetrics)
    candle_metrics: CandleValidationMetrics = field(default_factory=CandleValidationMetrics)
    option_chain_metrics: OptionChainValidationMetrics = field(default_factory=OptionChainValidationMetrics)
    active_findings: int = 0


@dataclass(frozen=True, slots=True)
class ValidationSessionSnapshot:
    session_id: str
    mode: ValidationMode
    lifecycle_state: ValidationLifecycleState
    started_at: datetime | None
    ended_at: datetime | None
    instruments: tuple[RuntimeInstrument, ...]
    expected_market_session: str
    counters: ValidationCounters
    active_findings: tuple[ValidationFinding, ...]
    component_freshness: tuple[ComponentFreshness, ...]
    instrument_summaries: tuple[InstrumentValidationSummary, ...]
    reconnect_summary: ReconnectSummary
    latency_summaries: tuple[LatencySummary, ...]
    final_summary: str
    failure_reason: str | None
    overall_health: ValidationHealth


@dataclass(frozen=True, slots=True)
class LiveValidationReport:
    session_id: str
    mode: ValidationMode
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: float
    instruments: tuple[RuntimeInstrument, ...]
    lifecycle_result: ValidationLifecycleState
    component_summaries: tuple[ComponentFreshness, ...]
    instrument_summaries: tuple[InstrumentValidationSummary, ...]
    latency_summaries: tuple[LatencySummary, ...]
    reconnect_summary: ReconnectSummary
    findings: tuple[ValidationFinding, ...]
    counters: ValidationCounters
    final_health: ValidationHealth
    outcome: ValidationOutcome
    report_path: Path | None = None

