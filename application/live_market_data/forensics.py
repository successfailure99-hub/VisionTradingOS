"""
Bounded durable live-feed incident telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from application.feed_incident_trace_store import BoundedJsonlTraceStore


DEFAULT_FEED_TRACE_PATH = Path("data") / "feed_forensics" / "nifty_feed_trace.jsonl"


@dataclass(frozen=True, slots=True)
class FeedIncidentTraceEvent:
    event_timestamp: datetime
    trading_date: date | None
    runtime_session_id: str
    instrument: str
    event: str
    connection_generation: int
    subscription_generation: int
    instrument_token: int | None
    exchange_timestamp: datetime | None
    normalized_timestamp: datetime | None
    last_delivered_market_timestamp: datetime | None
    raw_count: int
    normalized_count: int
    delivered_count: int
    rejected_count: int
    watchdog_state: str
    recovery_attempt: int
    error_class: str | None = None
    sanitized_error: str | None = None

    def __post_init__(self) -> None:
        _aware(self.event_timestamp, "event_timestamp")
        for name in ("exchange_timestamp", "normalized_timestamp", "last_delivered_market_timestamp"):
            value = getattr(self, name)
            if value is not None:
                _aware(value, name)


class FeedIncidentTrace:
    def __init__(self, path: Path | str | None = None, *, max_events: int = 512, redactions: tuple[str | None, ...] = ()):
        self._path = Path(path) if path is not None else DEFAULT_FEED_TRACE_PATH
        self._max_events = _positive_int(max_events, "max_events")
        self._redactions = tuple(value for value in redactions if value)
        self._store = BoundedJsonlTraceStore(self._path, max_events=self._max_events)
        self.last_error: str | None = None

    @property
    def path(self) -> Path:
        return self._path

    def record(self, event: FeedIncidentTraceEvent) -> bool:
        if not isinstance(event, FeedIncidentTraceEvent):
            raise TypeError("event must be FeedIncidentTraceEvent")
        try:
            self._store.record(_to_payload(event, self._redactions))
            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = _sanitize(f"{exc.__class__.__name__}: {exc}", self._redactions)
            return False


def _to_payload(event: FeedIncidentTraceEvent, redactions: tuple[str, ...]) -> dict[str, object]:
    payload = {}
    for field_name in event.__dataclass_fields__:
        value = getattr(event, field_name)
        if isinstance(value, datetime):
            payload[field_name] = value.isoformat()
        elif isinstance(value, date):
            payload[field_name] = value.isoformat()
        elif isinstance(value, str):
            payload[field_name] = _sanitize(value, redactions)
        else:
            payload[field_name] = value
    return payload


def _sanitize(message: str, redactions: tuple[str, ...]) -> str:
    sanitized = message
    for secret in redactions:
        if secret:
            sanitized = sanitized.replace(secret, "[REDACTED]")
    if "{" in sanitized or "}" in sanitized:
        sanitized = sanitized.split("{", 1)[0].strip()
    return sanitized


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive integer")
    return value
