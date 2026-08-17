"""
Bounded cross-feed timestamp telemetry for NIFTY/option-chain runtime evidence.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from application.feed_incident_trace_store import BoundedJsonlTraceStore


DEFAULT_CROSS_FEED_TRACE_PATH = Path("data") / "live_forensics" / "cross_feed_timestamp_trace.jsonl"


@dataclass(frozen=True, slots=True)
class CrossFeedTimestampObservation:
    observed_at: datetime
    instrument: str
    canonical_nifty_timestamp: datetime | None
    last_delivered_nifty_timestamp: datetime | None
    option_snapshot_timestamp: datetime
    option_snapshot_observed_at: datetime
    option_receipt_timestamp: datetime | None
    option_minus_canonical_seconds: float | None
    option_minus_last_delivered_seconds: float | None
    nifty_feed_age_seconds: float | None
    watchdog_state: str
    market_data_health: str
    websocket_state: str
    runtime_contract_status: str
    runtime_contract_reason: str
    option_expiry: date | None
    option_source: str
    session_date: date | None

    def __post_init__(self) -> None:
        _aware(self.observed_at, "observed_at")
        _aware(self.option_snapshot_timestamp, "option_snapshot_timestamp")
        _aware(self.option_snapshot_observed_at, "option_snapshot_observed_at")
        for field_name in (
            "canonical_nifty_timestamp",
            "last_delivered_nifty_timestamp",
            "option_receipt_timestamp",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _aware(value, field_name)
        for field_name in (
            "instrument",
            "watchdog_state",
            "market_data_health",
            "websocket_state",
            "runtime_contract_status",
            "runtime_contract_reason",
            "option_source",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")
        for field_name in (
            "option_minus_canonical_seconds",
            "option_minus_last_delivered_seconds",
            "nifty_feed_age_seconds",
        ):
            value = getattr(self, field_name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError(f"{field_name} must be numeric or None")
                object.__setattr__(self, field_name, float(value))
        if self.option_expiry is not None and (isinstance(self.option_expiry, datetime) or not isinstance(self.option_expiry, date)):
            raise TypeError("option_expiry must be date or None")
        if self.session_date is not None and (isinstance(self.session_date, datetime) or not isinstance(self.session_date, date)):
            raise TypeError("session_date must be date or None")


@dataclass(frozen=True, slots=True)
class CrossFeedTimestampSummary:
    sample_count: int
    latest_skew_seconds: float | None
    p50_skew_seconds: float | None
    p90_skew_seconds: float | None
    p95_skew_seconds: float | None
    p99_skew_seconds: float | None
    max_skew_seconds: float | None
    latest_nifty_feed_age_seconds: float | None
    latest_watchdog_state: str
    latest_market_data_health: str
    latest_runtime_contract_status: str
    latest_runtime_contract_reason: str
    latest_observed_at: datetime | None
    trace_path: str
    last_persistence_error: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.sample_count, bool) or not isinstance(self.sample_count, int) or self.sample_count < 0:
            raise ValueError("sample_count must be a non-negative integer")
        for field_name in (
            "latest_skew_seconds",
            "p50_skew_seconds",
            "p90_skew_seconds",
            "p95_skew_seconds",
            "p99_skew_seconds",
            "max_skew_seconds",
            "latest_nifty_feed_age_seconds",
        ):
            value = getattr(self, field_name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError(f"{field_name} must be numeric or None")
                object.__setattr__(self, field_name, float(value))
        for field_name in (
            "latest_watchdog_state",
            "latest_market_data_health",
            "latest_runtime_contract_status",
            "latest_runtime_contract_reason",
            "trace_path",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")
        if self.latest_observed_at is not None:
            _aware(self.latest_observed_at, "latest_observed_at")
        if self.last_persistence_error is not None and not isinstance(self.last_persistence_error, str):
            raise TypeError("last_persistence_error must be text or None")


class CrossFeedTimestampTelemetry:
    def __init__(
        self,
        path: Path | str | None = None,
        *,
        max_events: int = 2048,
        max_samples: int = 512,
        clock=None,
        store: BoundedJsonlTraceStore | None = None,
    ):
        self._path = Path(path) if path is not None else DEFAULT_CROSS_FEED_TRACE_PATH
        self._max_samples = _positive_int(max_samples, "max_samples")
        max_events = _positive_int(max_events, "max_events")
        self._clock = clock
        self._store = store or BoundedJsonlTraceStore(self._path, max_events=max_events)
        self._observations: deque[CrossFeedTimestampObservation] = deque(maxlen=self._max_samples)
        self.last_persistence_error: str | None = None

    @property
    def path(self) -> Path:
        return self._path

    def now(self) -> datetime:
        if self._clock is None:
            return datetime.now().astimezone()
        value = self._clock()
        _aware(value, "clock result")
        return value

    def record(self, observation: CrossFeedTimestampObservation) -> bool:
        if not isinstance(observation, CrossFeedTimestampObservation):
            raise TypeError("observation must be CrossFeedTimestampObservation")
        self._observations.append(observation)
        try:
            self._store.record(_payload(observation))
            self.last_persistence_error = None
            return True
        except Exception as exc:
            self.last_persistence_error = _safe_error(exc)
            return False

    def summary(self) -> CrossFeedTimestampSummary:
        observations = tuple(self._observations)
        latest = observations[-1] if observations else None
        skews = tuple(
            item.option_minus_canonical_seconds
            for item in observations
            if item.option_minus_canonical_seconds is not None
        )
        return CrossFeedTimestampSummary(
            sample_count=len(observations),
            latest_skew_seconds=None if latest is None else latest.option_minus_canonical_seconds,
            p50_skew_seconds=_percentile(skews, 50),
            p90_skew_seconds=_percentile(skews, 90),
            p95_skew_seconds=_percentile(skews, 95),
            p99_skew_seconds=_percentile(skews, 99),
            max_skew_seconds=max(skews) if skews else None,
            latest_nifty_feed_age_seconds=None if latest is None else latest.nifty_feed_age_seconds,
            latest_watchdog_state="-" if latest is None else latest.watchdog_state,
            latest_market_data_health="-" if latest is None else latest.market_data_health,
            latest_runtime_contract_status="-" if latest is None else latest.runtime_contract_status,
            latest_runtime_contract_reason="-" if latest is None else latest.runtime_contract_reason,
            latest_observed_at=None if latest is None else latest.observed_at,
            trace_path=str(self._path),
            last_persistence_error=self.last_persistence_error,
        )


def _payload(observation: CrossFeedTimestampObservation) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field_name in observation.__dataclass_fields__:
        value = getattr(observation, field_name)
        if isinstance(value, datetime):
            payload[field_name] = value.isoformat()
        elif isinstance(value, date):
            payload[field_name] = value.isoformat()
        else:
            payload[field_name] = value
    return payload


def _percentile(values: tuple[float, ...], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be positive integer")
    return value


def _safe_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    for token in ("access_token", "api_key", "api_secret", "request_token", "password", "pin", "totp"):
        message = message.replace(token, "[REDACTED]")
    if "{" in message or "}" in message:
        message = message.split("{", 1)[0].strip()
    return message
