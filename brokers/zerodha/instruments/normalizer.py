"""
Zerodha raw instrument record normalizer.
"""

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from math import isfinite

from brokers.zerodha.instruments.enums import ZerodhaInstrumentType
from brokers.zerodha.instruments.models import ZerodhaInstrumentRecord
from core.enums.exchange import Exchange


class ZerodhaInstrumentNormalizer:
    def normalize(
        self,
        raw_record: Mapping[str, object],
    ) -> ZerodhaInstrumentRecord:
        if not isinstance(raw_record, Mapping):
            raise TypeError("raw_record must be a mapping")
        exchange = Exchange.from_value(_text(raw_record.get("exchange"), "exchange"))
        segment = _text(raw_record.get("segment"), "segment")
        expiry = _expiry(raw_record.get("expiry"))
        instrument_type = _instrument_type(raw_record.get("instrument_type"), segment, expiry)
        return ZerodhaInstrumentRecord(
            instrument_token=_positive_int(raw_record.get("instrument_token"), "instrument_token"),
            exchange_token=_optional_positive_int(raw_record.get("exchange_token"), "exchange_token"),
            tradingsymbol=_text(raw_record.get("tradingsymbol"), "tradingsymbol"),
            name=_text(raw_record.get("name"), "name"),
            exchange=exchange,
            segment=segment,
            instrument_type=instrument_type,
            expiry=expiry,
            strike=_optional_non_negative_float(raw_record.get("strike"), "strike"),
            lot_size=_optional_positive_int(raw_record.get("lot_size"), "lot_size"),
            tick_size=_optional_positive_float(raw_record.get("tick_size"), "tick_size"),
        )

    def normalize_many(
        self,
        raw_records: Iterable[Mapping[str, object]],
    ) -> tuple[ZerodhaInstrumentRecord, ...]:
        if isinstance(raw_records, (str, bytes, Mapping)):
            raise TypeError("raw_records must be an iterable of mappings")
        return tuple(self.normalize(record) for record in raw_records)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _instrument_type(value: object, segment: str, expiry: date | None) -> ZerodhaInstrumentType:
    raw = "" if value is None else str(value).strip().upper()
    if raw in {"EQ"}:
        return ZerodhaInstrumentType.EQUITY
    if raw in {"FUT"}:
        return ZerodhaInstrumentType.FUTURE
    if raw in {"CE", "PE"}:
        return ZerodhaInstrumentType.OPTION
    if raw in {"INDEX", "INDICES"}:
        return ZerodhaInstrumentType.INDEX
    if not raw and expiry is None and segment.strip().upper() in {"INDICES", "NSE-INDICES", "BSE-INDICES"}:
        return ZerodhaInstrumentType.INDEX
    return ZerodhaInstrumentType.UNKNOWN


def _expiry(value: object) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise ValueError("expiry must be an ISO date string") from exc
    raise TypeError("expiry must be date, datetime, ISO date string, empty, or None")


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    return _positive_int(value, field_name)


def _number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _optional_non_negative_float(value: object, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    normalized = _number(value, field_name)
    if normalized < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return normalized


def _optional_positive_float(value: object, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    normalized = _number(value, field_name)
    if normalized <= 0:
        raise ValueError(f"{field_name} must be positive")
    return normalized
