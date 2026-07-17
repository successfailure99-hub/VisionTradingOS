"""
Zerodha live tick timestamp normalization helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import Mapping
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
DEFAULT_TIMESTAMP_FIELDS = ("exchange_timestamp", "last_trade_time", "timestamp")


class ZerodhaTimestampSource(str, Enum):
    RAW_FIELD = "RawField"
    CLOCK_FALLBACK = "ClockFallback"


@dataclass(frozen=True, slots=True)
class ZerodhaTimestampNormalization:
    timestamp: datetime
    source: ZerodhaTimestampSource
    field_name: str | None
    localized_naive: bool
    aware_input: bool
    clock_fallback: bool


def normalize_zerodha_tick_timestamp(
    raw_tick: Mapping[str, object],
    *,
    clock,
    field_names: tuple[str, ...] = DEFAULT_TIMESTAMP_FIELDS,
    allow_iso_text: bool = True,
) -> ZerodhaTimestampNormalization:
    if not isinstance(raw_tick, Mapping):
        raise TypeError("raw tick must be a mapping")
    for field_name in field_names:
        value = raw_tick.get(field_name)
        if value is not None:
            timestamp, localized, aware = _normalize_value(
                value,
                f"{field_name} timestamp",
                allow_iso_text=allow_iso_text,
            )
            return ZerodhaTimestampNormalization(
                timestamp=timestamp,
                source=ZerodhaTimestampSource.RAW_FIELD,
                field_name=field_name,
                localized_naive=localized,
                aware_input=aware,
                clock_fallback=False,
            )
    value = clock()
    timestamp, localized, aware = _normalize_value(value, "clock result", allow_iso_text=False)
    if localized:
        raise ValueError("clock result must be timezone-aware")
    return ZerodhaTimestampNormalization(
        timestamp=timestamp,
        source=ZerodhaTimestampSource.CLOCK_FALLBACK,
        field_name=None,
        localized_naive=False,
        aware_input=aware,
        clock_fallback=True,
    )


def _normalize_value(value: object, field_name: str, *, allow_iso_text: bool) -> tuple[datetime, bool, bool]:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be datetime")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=IST), True, False
        return value, False, True
    if isinstance(value, date):
        raise TypeError(f"{field_name} must include a time")
    if isinstance(value, str) and allow_iso_text:
        text = value.strip()
        if not text:
            raise ValueError(f"{field_name} must be non-empty")
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be ISO-8601 datetime") from exc
        return _normalize_value(parsed, field_name, allow_iso_text=False)
    raise TypeError(f"{field_name} must be datetime")


def default_zerodha_clock() -> datetime:
    return datetime.now(UTC)
