"""
Normalizer for raw Zerodha derivative option records.
"""

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from math import isfinite

from brokers.zerodha.options.enums import ZerodhaDerivativeVenue, ZerodhaOptionRight
from brokers.zerodha.options.models import ZerodhaOptionContract, venue_for_underlying
from core.enums.instrument import Instrument


NAME_MAP = {
    "NIFTY": Instrument.NIFTY,
    "NIFTY 50": Instrument.NIFTY,
    "BANKNIFTY": Instrument.BANKNIFTY,
    "NIFTY BANK": Instrument.BANKNIFTY,
    "SENSEX": Instrument.SENSEX,
    "S&P BSE SENSEX": Instrument.SENSEX,
}


class ZerodhaOptionContractNormalizer:
    def normalize(self, raw_record: Mapping[str, object]) -> ZerodhaOptionContract:
        if isinstance(raw_record, (str, bytes)) or not isinstance(raw_record, Mapping):
            raise TypeError("raw_record must be a mapping")
        venue = self._venue(raw_record.get("exchange"))
        right = self._right(raw_record.get("instrument_type"))
        segment = self._text(raw_record.get("segment"), "segment").upper()
        if segment != f"{venue.value}-OPT":
            raise ValueError("unsupported option segment")
        tradingsymbol = self._text(raw_record.get("tradingsymbol"), "tradingsymbol")
        raw_name = self._optional_text(raw_record.get("name"), "name")
        underlying = identify_underlying(
            {
                **raw_record,
                "name": raw_name,
                "tradingsymbol": tradingsymbol,
            }
        )
        if venue is not venue_for_underlying(underlying):
            raise ValueError("venue does not match underlying")
        normalized_name = (
            raw_name
            if raw_name is not None
            and NAME_MAP.get(" ".join(raw_name.upper().split())) is underlying
            else underlying.value
        )
        return ZerodhaOptionContract(
            instrument_token=self._positive_int(raw_record.get("instrument_token"), "instrument_token"),
            exchange_token=self._optional_positive_int(raw_record.get("exchange_token"), "exchange_token"),
            underlying=underlying,
            venue=venue,
            segment=segment,
            tradingsymbol=tradingsymbol,
            name=normalized_name,
            expiry=self._expiry(raw_record.get("expiry")),
            strike=self._positive_float(raw_record.get("strike"), "strike"),
            right=right,
            lot_size=self._positive_int(raw_record.get("lot_size"), "lot_size"),
            tick_size=self._positive_float(raw_record.get("tick_size"), "tick_size"),
        )

    def normalize_many(self, raw_records: Iterable[Mapping[str, object]]) -> tuple[ZerodhaOptionContract, ...]:
        if isinstance(raw_records, (str, bytes)):
            raise TypeError("raw_records must be iterable mappings")
        return tuple(self.normalize(record) for record in raw_records)

    def _venue(self, value: object) -> ZerodhaDerivativeVenue:
        text = self._text(value, "exchange").upper()
        try:
            return ZerodhaDerivativeVenue(text)
        except ValueError as exc:
            raise ValueError("unsupported derivative venue") from exc

    def _right(self, value: object) -> ZerodhaOptionRight:
        text = self._text(value, "instrument_type").upper()
        if text == "CE":
            return ZerodhaOptionRight.CALL
        if text == "PE":
            return ZerodhaOptionRight.PUT
        raise ValueError("unsupported option right")

    def _text(self, value: object, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a non-empty string")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must be a non-empty string")
        return normalized

    def _optional_text(self, value: object, field_name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be text, empty, or None")
        normalized = value.strip()
        return normalized or None

    def _positive_int(self, value: object, field_name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{field_name} must be a positive integer")
        if value <= 0:
            raise ValueError(f"{field_name} must be positive")
        return value

    def _optional_positive_int(self, value: object, field_name: str) -> int | None:
        if value is None or value == "":
            return None
        return self._positive_int(value, field_name)

    def _positive_float(self, value: object, field_name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{field_name} must be a finite positive number")
        normalized = float(value)
        if not isfinite(normalized) or normalized <= 0:
            raise ValueError(f"{field_name} must be finite and positive")
        return normalized

    def _expiry(self, value: object) -> date:
        if isinstance(value, datetime):
            raise TypeError("expiry must be date")
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip())
            except ValueError as exc:
                raise ValueError("malformed expiry") from exc
        raise TypeError("expiry must be date")


def identify_underlying(raw_record: Mapping[str, object]) -> Instrument:
    name = raw_record.get("name")
    if isinstance(name, str):
        normalized_name = " ".join(name.strip().upper().split())
        if normalized_name in NAME_MAP:
            return NAME_MAP[normalized_name]
    symbol = raw_record.get("tradingsymbol")
    if not isinstance(symbol, str):
        raise ValueError("unsupported option underlying")
    normalized_symbol = symbol.strip().upper()
    if normalized_symbol.startswith("BANKNIFTY"):
        return Instrument.BANKNIFTY
    if normalized_symbol.startswith("NIFTY"):
        return Instrument.NIFTY
    if normalized_symbol.startswith("SENSEX"):
        return Instrument.SENSEX
    raise ValueError("unsupported option underlying")


def is_candidate_record(
    raw_record: Mapping[str, object],
    underlyings: tuple[Instrument, ...],
    venues: set[ZerodhaDerivativeVenue],
) -> bool:
    if isinstance(raw_record, (str, bytes)) or not isinstance(raw_record, Mapping):
        return False
    try:
        exchange = str(raw_record.get("exchange", "")).strip().upper()
        instrument_type = str(raw_record.get("instrument_type", "")).strip().upper()
        if ZerodhaDerivativeVenue(exchange) not in venues or instrument_type not in {"CE", "PE"}:
            return False
        return identify_underlying(raw_record) in underlyings
    except Exception:
        return False
