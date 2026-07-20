"""
Immutable live shadow market session coordinator models.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from adapters.zerodha.enums import ZerodhaConnectionState
from application.enums import RuntimeInstrument

from .enums import LiveShadowSessionState, LiveShadowSessionStatus


SUPPORTED_LIVE_SHADOW_INSTRUMENTS = (
    RuntimeInstrument.NIFTY,
    RuntimeInstrument.BANKNIFTY,
    RuntimeInstrument.SENSEX,
)


def _aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _text(value, "optional text")


def normalize_instrument(value: str | RuntimeInstrument) -> RuntimeInstrument:
    if isinstance(value, RuntimeInstrument):
        instrument = value
    elif isinstance(value, str):
        normalized = _text(value, "instrument").upper()
        try:
            instrument = RuntimeInstrument(normalized)
        except ValueError as exc:
            raise ValueError("unsupported live shadow instrument") from exc
    else:
        raise TypeError("instrument must be text or RuntimeInstrument")
    if instrument not in SUPPORTED_LIVE_SHADOW_INSTRUMENTS:
        raise ValueError("unsupported live shadow instrument")
    return instrument


def normalize_instruments(values: tuple[str | RuntimeInstrument, ...]) -> tuple[RuntimeInstrument, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, tuple) or not values:
        raise ValueError("instruments must be a non-empty tuple")
    normalized = tuple(normalize_instrument(value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError("instruments must not contain duplicates")
    return tuple(instrument for instrument in SUPPORTED_LIVE_SHADOW_INSTRUMENTS if instrument in normalized)


def _metadata(value: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, tuple):
        raise TypeError("metadata must be a tuple")
    normalized = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("metadata entries must be key/value tuples")
        normalized.append((_text(item[0], "metadata key"), _text(item[1], "metadata value")))
    return tuple(sorted(normalized))


def _non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class LiveShadowSessionRequest:
    session_id: str
    started_at: datetime
    instruments: tuple[str, ...] = tuple(instrument.value for instrument in SUPPORTED_LIVE_SHADOW_INSTRUMENTS)
    correlation_id: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _text(self.session_id, "session_id"))
        object.__setattr__(self, "started_at", _aware(self.started_at, "started_at"))
        normalized = normalize_instruments(self.instruments)
        object.__setattr__(self, "instruments", tuple(instrument.value for instrument in normalized))
        object.__setattr__(self, "correlation_id", _optional_text(self.correlation_id))
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "session_id": self.session_id,
                "started_at": self.started_at.isoformat(),
                "instruments": self.instruments,
                "correlation_id": self.correlation_id,
                "metadata": self.metadata,
            }
        )


@dataclass(frozen=True, slots=True)
class LiveShadowInstrumentResult:
    instrument: RuntimeInstrument
    shadow_session_id: str
    market_tick_count: int
    accepted_tick_count: int
    rejected_tick_count: int
    shadow_observation_count: int
    shadow_status: str
    shadow_lifecycle: str
    shadow_summary: object
    last_tick_at: datetime | None
    primary_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument", normalize_instrument(self.instrument))
        object.__setattr__(self, "shadow_session_id", _text(self.shadow_session_id, "shadow_session_id"))
        for field_name in (
            "market_tick_count",
            "accepted_tick_count",
            "rejected_tick_count",
            "shadow_observation_count",
        ):
            object.__setattr__(self, field_name, _non_negative_int(getattr(self, field_name), field_name))
        object.__setattr__(self, "shadow_status", _text(self.shadow_status, "shadow_status"))
        object.__setattr__(self, "shadow_lifecycle", _text(self.shadow_lifecycle, "shadow_lifecycle"))
        if self.last_tick_at is not None:
            object.__setattr__(self, "last_tick_at", _aware(self.last_tick_at, "last_tick_at"))
        object.__setattr__(self, "primary_reason", _text(self.primary_reason, "primary_reason"))


@dataclass(frozen=True, slots=True)
class LiveShadowSessionReport:
    session_id: str
    started_at: datetime
    ended_at: datetime
    state: LiveShadowSessionState
    status: LiveShadowSessionStatus
    primary_reason: str
    instruments: tuple[RuntimeInstrument, ...]
    instrument_results: tuple[LiveShadowInstrumentResult, ...]
    zerodha_state: ZerodhaConnectionState
    zerodha_authenticated: bool
    zerodha_connected: bool
    zerodha_received_tick_count: int
    zerodha_published_tick_count: int
    zerodha_rejected_tick_count: int
    zerodha_duplicate_tick_count: int
    total_market_tick_count: int
    total_accepted_tick_count: int
    total_rejected_tick_count: int
    total_shadow_observation_count: int
    broker_order_calls: int = 0
    mutation_calls: int = 0
    live_order_submission_enabled: bool = False
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _text(self.session_id, "session_id"))
        object.__setattr__(self, "started_at", _aware(self.started_at, "started_at"))
        object.__setattr__(self, "ended_at", _aware(self.ended_at, "ended_at"))
        if self.ended_at < self.started_at:
            raise ValueError("ended_at cannot be before started_at")
        if not isinstance(self.state, LiveShadowSessionState):
            raise TypeError("state must be LiveShadowSessionState")
        if not isinstance(self.status, LiveShadowSessionStatus):
            raise TypeError("status must be LiveShadowSessionStatus")
        object.__setattr__(self, "primary_reason", _text(self.primary_reason, "primary_reason"))
        instruments = tuple(normalize_instrument(instrument) for instrument in self.instruments)
        if len(set(instruments)) != len(instruments):
            raise ValueError("report instruments must be unique")
        object.__setattr__(self, "instruments", instruments)
        results = tuple(self.instrument_results)
        if any(not isinstance(result, LiveShadowInstrumentResult) for result in results):
            raise TypeError("instrument_results must contain LiveShadowInstrumentResult values")
        object.__setattr__(self, "instrument_results", results)
        if not isinstance(self.zerodha_state, ZerodhaConnectionState):
            raise TypeError("zerodha_state must be ZerodhaConnectionState")
        for field_name in ("zerodha_authenticated", "zerodha_connected", "live_order_submission_enabled"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be bool")
        for field_name in (
            "zerodha_received_tick_count",
            "zerodha_published_tick_count",
            "zerodha_rejected_tick_count",
            "zerodha_duplicate_tick_count",
            "total_market_tick_count",
            "total_accepted_tick_count",
            "total_rejected_tick_count",
            "total_shadow_observation_count",
            "broker_order_calls",
            "mutation_calls",
        ):
            object.__setattr__(self, field_name, _non_negative_int(getattr(self, field_name), field_name))
        if self.broker_order_calls != 0 or self.mutation_calls != 0 or self.live_order_submission_enabled is not False:
            raise ValueError("live shadow report must remain read-only")
        object.__setattr__(self, "correlation_id", _optional_text(self.correlation_id))


@dataclass(frozen=True, slots=True)
class LiveShadowSessionSnapshot:
    enabled: bool
    state: LiveShadowSessionState
    active_session_id: str | None
    active_instruments: tuple[RuntimeInstrument, ...]
    started_at: datetime | None
    last_tick_at: datetime | None
    market_tick_count: int
    accepted_tick_count: int
    rejected_tick_count: int
    shadow_observation_count: int
    last_report: LiveShadowSessionReport | None
    failure_code: str | None
    broker_order_calls: int = 0
    mutation_calls: int = 0
    live_order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool")
        if not isinstance(self.state, LiveShadowSessionState):
            raise TypeError("state must be LiveShadowSessionState")
        object.__setattr__(self, "active_session_id", _optional_text(self.active_session_id))
        active = tuple(normalize_instrument(instrument) for instrument in self.active_instruments)
        if len(set(active)) != len(active):
            raise ValueError("active_instruments must be unique")
        object.__setattr__(self, "active_instruments", active)
        if self.started_at is not None:
            object.__setattr__(self, "started_at", _aware(self.started_at, "started_at"))
        if self.last_tick_at is not None:
            object.__setattr__(self, "last_tick_at", _aware(self.last_tick_at, "last_tick_at"))
        for field_name in (
            "market_tick_count",
            "accepted_tick_count",
            "rejected_tick_count",
            "shadow_observation_count",
            "broker_order_calls",
            "mutation_calls",
        ):
            object.__setattr__(self, field_name, _non_negative_int(getattr(self, field_name), field_name))
        if self.last_report is not None and not isinstance(self.last_report, LiveShadowSessionReport):
            raise TypeError("last_report must be LiveShadowSessionReport or None")
        object.__setattr__(self, "failure_code", _optional_text(self.failure_code))
        if self.broker_order_calls != 0 or self.mutation_calls != 0 or self.live_order_submission_enabled is not False:
            raise ValueError("live shadow snapshot must remain read-only")
