"""
Canonical production runtime contract validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from application.enums import RuntimeInstrument
from core.enums.instrument import Instrument


IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class RuntimeContractViolation:
    object_name: str
    reason: str
    owner: str
    producer: str
    consumer: str
    expected: str
    actual: str

    def __post_init__(self) -> None:
        for field_name in ("object_name", "reason", "owner", "producer", "consumer", "expected", "actual"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")


@dataclass(frozen=True, slots=True)
class RuntimeIntegrityViolation:
    object_name: str
    invariant: str
    owner: str
    producer: str
    consumer: str
    expected: str
    actual: str
    timestamp: datetime | None
    instrument: str
    timeframe: str
    recovery_action: str

    def __post_init__(self) -> None:
        for field_name in (
            "object_name",
            "invariant",
            "owner",
            "producer",
            "consumer",
            "expected",
            "actual",
            "instrument",
            "timeframe",
            "recovery_action",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")
        if self.timestamp is not None and not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be datetime or None")


@dataclass(frozen=True, slots=True)
class RuntimeContractReport:
    status: str
    owner: str
    producer: str
    consumer: str
    object_name: str
    checked_at: datetime | None
    violations: tuple[RuntimeContractViolation, ...] = ()
    integrity_violations: tuple[RuntimeIntegrityViolation, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("status", "owner", "producer", "consumer", "object_name"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")
        if self.checked_at is not None and not isinstance(self.checked_at, datetime):
            raise TypeError("checked_at must be datetime or None")
        violations = tuple(self.violations)
        for violation in violations:
            if not isinstance(violation, RuntimeContractViolation):
                raise TypeError("violations must contain RuntimeContractViolation values")
        object.__setattr__(self, "violations", violations)
        integrity_violations = tuple(self.integrity_violations)
        for violation in integrity_violations:
            if not isinstance(violation, RuntimeIntegrityViolation):
                raise TypeError("integrity_violations must contain RuntimeIntegrityViolation values")
        object.__setattr__(self, "integrity_violations", integrity_violations)

    @property
    def valid(self) -> bool:
        return self.status == "VALID" and not self.violations and not self.integrity_violations

    @property
    def blocking_reason(self) -> str:
        if self.valid:
            return "-"
        if self.violations:
            first = self.violations[0]
            return f"{first.object_name}: {first.reason}"
        first_integrity = self.integrity_violations[0]
        return f"{first_integrity.object_name}: {first_integrity.invariant}"


@dataclass(frozen=True, slots=True)
class RuntimeContractContext:
    instrument: RuntimeInstrument
    timeframe: str
    runtime_timestamp: datetime | None
    trading_date: object
    session: object | None = None
    previous_runtime_timestamp: datetime | None = None
    owner: str = "SymbolRuntime"
    producer: str = "RuntimeSnapshot"
    consumer: str = "Dashboard"

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe must be non-empty text")
        object.__setattr__(self, "timeframe", self.timeframe.strip())
        for field_name in ("runtime_timestamp", "previous_runtime_timestamp"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be datetime or None")
        for field_name in ("owner", "producer", "consumer"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")


@dataclass(frozen=True, slots=True)
class RuntimeContractSubject:
    instrument: RuntimeInstrument
    timeframe: str | None
    timestamp: datetime | None
    trading_date: object = None
    session: object | None = None


class RuntimeContractValidator:
    def validate_many(self, items: tuple[tuple[str, object, str, str, str], ...], context: RuntimeContractContext) -> RuntimeContractReport:
        if not isinstance(context, RuntimeContractContext):
            raise TypeError("context must be RuntimeContractContext")
        violations: list[RuntimeContractViolation] = []
        for object_name, snapshot, owner, producer, consumer in items:
            if snapshot is None:
                continue
            violations.extend(self._validate_one(object_name, snapshot, context, owner, producer, consumer))
        return RuntimeContractReport(
            status="VALID" if not violations else "FAILED",
            owner=context.owner,
            producer=context.producer,
            consumer=context.consumer,
            object_name="RuntimeSnapshot",
            checked_at=context.runtime_timestamp,
            violations=tuple(violations),
        )

    def _validate_one(
        self,
        object_name: str,
        snapshot: object,
        context: RuntimeContractContext,
        owner: str,
        producer: str,
        consumer: str,
    ) -> tuple[RuntimeContractViolation, ...]:
        violations: list[RuntimeContractViolation] = []
        candle_interval = _candle_interval(snapshot) if object_name == "Candle" else None
        timestamp = candle_interval[0] if candle_interval is not None else _timestamp(snapshot)
        if timestamp is not None:
            if not _aware(timestamp):
                violations.append(_violation(object_name, "Timezone mismatch", owner, producer, consumer, "timezone-aware Asia/Kolkata-compatible timestamp", repr(timestamp)))
            if candle_interval is not None:
                violations.extend(_candle_interval_violations(candle_interval, context, object_name, owner, producer, consumer))
            elif context.runtime_timestamp is not None and _same_awareness(timestamp, context.runtime_timestamp) and timestamp > context.runtime_timestamp:
                violations.append(_violation(object_name, "Future timestamp", owner, producer, consumer, f"<= {context.runtime_timestamp.isoformat()}", timestamp.isoformat()))
        if object_name == "RuntimeSnapshot" and timestamp is not None and context.previous_runtime_timestamp is not None:
            if _same_awareness(timestamp, context.previous_runtime_timestamp) and timestamp < context.previous_runtime_timestamp:
                violations.append(_violation(object_name, "Runtime ordering mismatch", owner, producer, consumer, f">= {context.previous_runtime_timestamp.isoformat()}", timestamp.isoformat()))
        actual_instrument = _instrument(snapshot)
        if actual_instrument is not None and actual_instrument != context.instrument.value:
            violations.append(_violation(object_name, "Instrument mismatch", owner, producer, consumer, context.instrument.value, actual_instrument))
        actual_timeframe = _timeframe(snapshot)
        if actual_timeframe is not None and actual_timeframe != context.timeframe:
            violations.append(_violation(object_name, "Timeframe mismatch", owner, producer, consumer, context.timeframe, actual_timeframe))
        actual_date = _trading_date(snapshot, timestamp)
        if context.trading_date is not None and actual_date is not None and actual_date != context.trading_date:
            violations.append(_violation(object_name, "Trading date mismatch", owner, producer, consumer, str(context.trading_date), str(actual_date)))
        actual_session = _session(snapshot)
        if context.session is not None and actual_session is not None:
            expected_session = _session_signature(context.session)
            observed_session = _session_signature(actual_session)
            if expected_session != observed_session:
                violations.append(_violation(object_name, "Session mismatch", owner, producer, consumer, str(expected_session), str(observed_session)))
        return tuple(violations)


def _violation(object_name: str, reason: str, owner: str, producer: str, consumer: str, expected: str, actual: str) -> RuntimeContractViolation:
    return RuntimeContractViolation(object_name, reason, owner, producer, consumer, expected, actual)


def _timestamp(snapshot: object) -> datetime | None:
    for field_name in ("snapshot_created_at", "timestamp", "updated_at", "end_time", "journal_write_timestamp"):
        value = getattr(snapshot, field_name, None)
        if isinstance(value, datetime):
            return value
    latest = getattr(snapshot, "latest_candle", None)
    value = getattr(latest, "end_time", None)
    return value if isinstance(value, datetime) else None


def _candle_interval(snapshot: object) -> tuple[datetime, datetime] | None:
    start_time = getattr(snapshot, "start_time", None)
    end_time = getattr(snapshot, "end_time", None)
    if isinstance(start_time, datetime) and isinstance(end_time, datetime):
        return (start_time, end_time)
    return None


def _candle_interval_violations(
    interval: tuple[datetime, datetime],
    context: RuntimeContractContext,
    object_name: str,
    owner: str,
    producer: str,
    consumer: str,
) -> tuple[RuntimeContractViolation, ...]:
    start_time, end_time = interval
    violations: list[RuntimeContractViolation] = []
    if not _aware(end_time):
        violations.append(_violation(object_name, "Timezone mismatch", owner, producer, consumer, "timezone-aware Asia/Kolkata-compatible end_time", repr(end_time)))
        return tuple(violations)
    if not _same_awareness(start_time, end_time):
        violations.append(_violation(object_name, "Timezone mismatch", owner, producer, consumer, "matching candle start_time/end_time timezone awareness", f"{start_time!r} / {end_time!r}"))
    if end_time <= start_time:
        violations.append(_violation(object_name, "Invalid candle interval", owner, producer, consumer, "end_time after start_time", f"{start_time.isoformat()} -> {end_time.isoformat()}"))
    runtime_timestamp = context.runtime_timestamp
    if runtime_timestamp is None or not _same_awareness(start_time, runtime_timestamp):
        return tuple(violations)
    if start_time > runtime_timestamp:
        violations.append(_violation(object_name, "Future timestamp", owner, producer, consumer, f"start_time <= {runtime_timestamp.isoformat()}", start_time.isoformat()))
        return tuple(violations)
    if end_time > runtime_timestamp and not start_time <= runtime_timestamp < end_time:
        violations.append(_violation(object_name, "Future timestamp", owner, producer, consumer, f"active candle interval contains {runtime_timestamp.isoformat()}", f"{start_time.isoformat()} -> {end_time.isoformat()}"))
    return tuple(violations)


def _trading_date(snapshot: object, timestamp: datetime | None):
    for field_name in ("trading_date", "cpr_trading_date", "adr_trading_date", "vwap_trading_date"):
        value = getattr(snapshot, field_name, None)
        if value is not None:
            return value
    if timestamp is not None and _aware(timestamp):
        return timestamp.astimezone(IST).date()
    return None


def _instrument(snapshot: object) -> str | None:
    value = getattr(snapshot, "instrument", None) or getattr(snapshot, "symbol", None) or getattr(snapshot, "underlying", None)
    if isinstance(value, RuntimeInstrument):
        return value.value
    if isinstance(value, Instrument):
        return value.value
    if isinstance(value, str):
        return value.strip().upper() or None
    return None


def _timeframe(snapshot: object) -> str | None:
    value = getattr(snapshot, "timeframe", None)
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, str):
        return value.strip() or None
    return None


def _session(snapshot: object) -> object | None:
    return getattr(snapshot, "runtime_session", None) or getattr(snapshot, "trading_session", None) or getattr(snapshot, "session", None)


def _session_signature(session: object) -> tuple[str | None, str | None, object, str | None]:
    instrument = _instrument(session)
    exchange = getattr(session, "exchange", None)
    if isinstance(exchange, str):
        exchange = exchange.strip().upper() or None
    else:
        exchange = None
    trading_date = getattr(session, "trading_date", None)
    status = getattr(session, "status", None)
    if isinstance(status, str):
        status = status.strip().upper() or None
    else:
        status = None
    return (instrument, exchange, trading_date, status)


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _same_awareness(left: datetime, right: datetime) -> bool:
    return _aware(left) == _aware(right)
