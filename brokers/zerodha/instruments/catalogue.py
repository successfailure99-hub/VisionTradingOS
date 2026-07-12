"""
In-memory Zerodha instrument catalogue.
"""

from datetime import date
from threading import RLock

from brokers.zerodha.instruments.enums import ZerodhaInstrumentType
from brokers.zerodha.instruments.models import ZerodhaInstrumentRecord
from core.enums.exchange import Exchange


class ZerodhaInstrumentCatalogue:
    def __init__(
        self,
        records: tuple[ZerodhaInstrumentRecord, ...] = (),
    ):
        self._lock = RLock()
        self._records: tuple[ZerodhaInstrumentRecord, ...] = ()
        self._by_token: dict[int, ZerodhaInstrumentRecord] = {}
        self.replace(records)

    def replace(
        self,
        records: tuple[ZerodhaInstrumentRecord, ...],
    ) -> tuple[ZerodhaInstrumentRecord, ...]:
        normalized = _validate_records(records)
        by_token = {record.instrument_token: record for record in normalized}
        if len(by_token) != len(normalized):
            raise ValueError("duplicate instrument token")
        with self._lock:
            self._records = normalized
            self._by_token = by_token
            return self._records

    def all(self) -> tuple[ZerodhaInstrumentRecord, ...]:
        with self._lock:
            return self._records

    def by_token(
        self,
        instrument_token: int,
    ) -> ZerodhaInstrumentRecord | None:
        if isinstance(instrument_token, bool) or not isinstance(instrument_token, int):
            raise TypeError("instrument_token must be int")
        with self._lock:
            return self._by_token.get(instrument_token)

    def by_exchange(
        self,
        exchange: Exchange,
    ) -> tuple[ZerodhaInstrumentRecord, ...]:
        if not isinstance(exchange, Exchange):
            raise TypeError("exchange must be Exchange")
        with self._lock:
            return tuple(record for record in self._records if record.exchange is exchange)

    def find(
        self,
        *,
        exchange: Exchange | None = None,
        tradingsymbol: str | None = None,
        name: str | None = None,
        segment: str | None = None,
        instrument_type: ZerodhaInstrumentType | None = None,
        expiry: date | None = None,
    ) -> tuple[ZerodhaInstrumentRecord, ...]:
        if exchange is not None and not isinstance(exchange, Exchange):
            raise TypeError("exchange must be Exchange or None")
        if instrument_type is not None and not isinstance(instrument_type, ZerodhaInstrumentType):
            raise TypeError("instrument_type must be ZerodhaInstrumentType or None")
        symbol_key = _key(tradingsymbol) if tradingsymbol is not None else None
        name_key = _key(name) if name is not None else None
        segment_key = _key(segment) if segment is not None else None
        with self._lock:
            records = self._records
            if exchange is not None:
                records = tuple(record for record in records if record.exchange is exchange)
            if symbol_key is not None:
                records = tuple(record for record in records if _key(record.tradingsymbol) == symbol_key)
            if name_key is not None:
                records = tuple(record for record in records if _key(record.name) == name_key)
            if segment_key is not None:
                records = tuple(record for record in records if _key(record.segment) == segment_key)
            if instrument_type is not None:
                records = tuple(record for record in records if record.instrument_type is instrument_type)
            if expiry is not None:
                records = tuple(record for record in records if record.expiry == expiry)
            return records

    def clear(self) -> tuple[ZerodhaInstrumentRecord, ...]:
        with self._lock:
            self._records = ()
            self._by_token = {}
            return self._records


def _validate_records(records: tuple[ZerodhaInstrumentRecord, ...]) -> tuple[ZerodhaInstrumentRecord, ...]:
    normalized = tuple(records)
    if any(not isinstance(record, ZerodhaInstrumentRecord) for record in normalized):
        raise TypeError("records must contain ZerodhaInstrumentRecord values")
    return normalized


def _key(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("text filter must be str")
    normalized = value.strip()
    if not normalized:
        raise ValueError("text filter must be non-empty")
    return normalized.casefold()
