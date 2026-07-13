"""
Immutable Zerodha option-contract models.
"""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaSubscriptionMode
from brokers.zerodha.options.enums import (
    ZerodhaDerivativeVenue,
    ZerodhaExpiryKind,
    ZerodhaOptionDiscoveryStatus,
    ZerodhaOptionRight,
)
from core.enums.instrument import Instrument


SUPPORTED_UNDERLYINGS = (Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX)
UNDERLYING_VENUES = {
    Instrument.NIFTY: ZerodhaDerivativeVenue.NFO,
    Instrument.BANKNIFTY: ZerodhaDerivativeVenue.NFO,
    Instrument.SENSEX: ZerodhaDerivativeVenue.BFO,
}
OPTION_SEGMENTS = {"NFO-OPT", "BFO-OPT"}


def require_supported_underlying(value: Instrument) -> Instrument:
    if not isinstance(value, Instrument):
        raise TypeError("underlying must be Instrument")
    if value not in SUPPORTED_UNDERLYINGS:
        raise ValueError("unsupported option underlying")
    return value


def venue_for_underlying(underlying: Instrument) -> ZerodhaDerivativeVenue:
    require_supported_underlying(underlying)
    return UNDERLYING_VENUES[underlying]


def require_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be a positive integer")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


def require_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be a non-negative integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def require_positive_float(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a finite positive number")
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{field_name} must be finite and positive")
    return normalized


def require_date(value: date, field_name: str) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError(f"{field_name} must be date")
    return value


def require_aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


@dataclass(frozen=True, slots=True)
class ZerodhaOptionContract:
    instrument_token: int
    exchange_token: int | None
    underlying: Instrument
    venue: ZerodhaDerivativeVenue
    segment: str
    tradingsymbol: str
    name: str
    expiry: date
    strike: float
    right: ZerodhaOptionRight
    lot_size: int
    tick_size: float

    def __post_init__(self) -> None:
        token = require_positive_int(self.instrument_token, "instrument_token")
        exchange_token = self.exchange_token
        if exchange_token is not None:
            exchange_token = require_positive_int(exchange_token, "exchange_token")
        underlying = require_supported_underlying(self.underlying)
        if not isinstance(self.venue, ZerodhaDerivativeVenue):
            raise TypeError("venue must be ZerodhaDerivativeVenue")
        if self.venue is not venue_for_underlying(underlying):
            raise ValueError("venue does not match underlying")
        segment = _text(self.segment, "segment").upper()
        if segment not in OPTION_SEGMENTS or not segment.startswith(self.venue.value):
            raise ValueError("segment must be a supported option segment")
        if not isinstance(self.right, ZerodhaOptionRight):
            raise TypeError("right must be ZerodhaOptionRight")
        object.__setattr__(self, "instrument_token", token)
        object.__setattr__(self, "exchange_token", exchange_token)
        object.__setattr__(self, "segment", segment)
        object.__setattr__(self, "tradingsymbol", _text(self.tradingsymbol, "tradingsymbol"))
        object.__setattr__(self, "name", _text(self.name, "name"))
        object.__setattr__(self, "expiry", require_date(self.expiry, "expiry"))
        object.__setattr__(self, "strike", require_positive_float(self.strike, "strike"))
        object.__setattr__(self, "lot_size", require_positive_int(self.lot_size, "lot_size"))
        object.__setattr__(self, "tick_size", require_positive_float(self.tick_size, "tick_size"))


@dataclass(frozen=True, slots=True)
class ZerodhaExpiry:
    underlying: Instrument
    expiry: date
    kind: ZerodhaExpiryKind
    contract_count: int
    strike_count: int
    first_strike: float
    last_strike: float

    def __post_init__(self) -> None:
        require_supported_underlying(self.underlying)
        require_date(self.expiry, "expiry")
        if not isinstance(self.kind, ZerodhaExpiryKind):
            raise TypeError("kind must be ZerodhaExpiryKind")
        require_positive_int(self.contract_count, "contract_count")
        require_positive_int(self.strike_count, "strike_count")
        first = require_positive_float(self.first_strike, "first_strike")
        last = require_positive_float(self.last_strike, "last_strike")
        if first > last:
            raise ValueError("first_strike must be <= last_strike")
        object.__setattr__(self, "first_strike", first)
        object.__setattr__(self, "last_strike", last)


@dataclass(frozen=True, slots=True)
class ZerodhaOptionPair:
    underlying: Instrument
    expiry: ZerodhaExpiry
    strike: float
    call: ZerodhaOptionContract
    put: ZerodhaOptionContract

    def __post_init__(self) -> None:
        underlying = require_supported_underlying(self.underlying)
        if not isinstance(self.expiry, ZerodhaExpiry):
            raise TypeError("expiry must be ZerodhaExpiry")
        strike = require_positive_float(self.strike, "strike")
        if not isinstance(self.call, ZerodhaOptionContract) or not isinstance(self.put, ZerodhaOptionContract):
            raise TypeError("call and put must be ZerodhaOptionContract")
        if self.call.right is not ZerodhaOptionRight.CALL or self.put.right is not ZerodhaOptionRight.PUT:
            raise ValueError("pair requires CE call and PE put")
        if self.call.instrument_token == self.put.instrument_token:
            raise ValueError("call and put tokens must differ")
        for contract in (self.call, self.put):
            if contract.underlying is not underlying:
                raise ValueError("contract underlying mismatch")
            if contract.expiry != self.expiry.expiry:
                raise ValueError("contract expiry mismatch")
            if contract.strike != strike:
                raise ValueError("contract strike mismatch")
            if contract.venue is not self.call.venue:
                raise ValueError("contract venue mismatch")
        object.__setattr__(self, "strike", strike)


@dataclass(frozen=True, slots=True)
class ZerodhaOptionUniverse:
    underlying: Instrument
    venue: ZerodhaDerivativeVenue
    expiry: ZerodhaExpiry
    underlying_price: float
    atm_strike: float
    strike_step: float
    pairs: tuple[ZerodhaOptionPair, ...]
    subscriptions: tuple[ZerodhaInstrumentSubscription, ...]
    resolved_at: datetime

    def __post_init__(self) -> None:
        underlying = require_supported_underlying(self.underlying)
        if not isinstance(self.venue, ZerodhaDerivativeVenue):
            raise TypeError("venue must be ZerodhaDerivativeVenue")
        if self.venue is not venue_for_underlying(underlying):
            raise ValueError("venue does not match underlying")
        if not isinstance(self.expiry, ZerodhaExpiry):
            raise TypeError("expiry must be ZerodhaExpiry")
        pairs = tuple(self.pairs)
        if not pairs:
            raise ValueError("at least one option pair is required")
        strikes = tuple(pair.strike for pair in pairs)
        if strikes != tuple(sorted(strikes)):
            raise ValueError("pairs must be sorted by strike")
        if len(set(strikes)) != len(strikes):
            raise ValueError("duplicate pair strike")
        atm_strike = require_positive_float(self.atm_strike, "atm_strike")
        if atm_strike not in strikes:
            raise ValueError("ATM strike must be included")
        for pair in pairs:
            if pair.underlying is not underlying or pair.expiry != self.expiry:
                raise ValueError("pair does not match universe")
        subscriptions = tuple(self.subscriptions)
        if len(subscriptions) != len(pairs) * 2:
            raise ValueError("subscriptions must contain two entries per pair")
        expected = []
        for pair in pairs:
            expected.extend((pair.call.instrument_token, pair.put.instrument_token))
        if tuple(item.instrument_token for item in subscriptions) != tuple(expected):
            raise ValueError("subscription token order must match CE/PE pairs")
        if any(item.instrument is not underlying for item in subscriptions):
            raise ValueError("subscription instrument mismatch")
        if any(not isinstance(item.mode, ZerodhaSubscriptionMode) for item in subscriptions):
            raise TypeError("subscription mode mismatch")
        require_aware(self.resolved_at, "resolved_at")
        object.__setattr__(self, "underlying_price", require_positive_float(self.underlying_price, "underlying_price"))
        object.__setattr__(self, "atm_strike", atm_strike)
        object.__setattr__(self, "strike_step", require_positive_float(self.strike_step, "strike_step"))
        object.__setattr__(self, "pairs", pairs)
        object.__setattr__(self, "subscriptions", subscriptions)


@dataclass(frozen=True, slots=True)
class ZerodhaOptionDiscoverySnapshot:
    status: ZerodhaOptionDiscoveryStatus
    record_count: int
    supported_contract_count: int
    available_underlyings: tuple[Instrument, ...]
    available_expiry_count: int
    loaded_venues: tuple[ZerodhaDerivativeVenue, ...]
    loaded_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ZerodhaOptionDiscoveryStatus):
            raise TypeError("status must be ZerodhaOptionDiscoveryStatus")
        require_non_negative_int(self.record_count, "record_count")
        require_non_negative_int(self.supported_contract_count, "supported_contract_count")
        require_non_negative_int(self.available_expiry_count, "available_expiry_count")
        underlyings = tuple(self.available_underlyings)
        for underlying in underlyings:
            require_supported_underlying(underlying)
        venues = tuple(self.loaded_venues)
        if any(not isinstance(venue, ZerodhaDerivativeVenue) for venue in venues):
            raise TypeError("loaded_venues must contain ZerodhaDerivativeVenue values")
        if self.loaded_at is not None:
            require_aware(self.loaded_at, "loaded_at")
        if self.last_error is not None and not isinstance(self.last_error, str):
            raise TypeError("last_error must be str or None")
        object.__setattr__(self, "available_underlyings", underlyings)
        object.__setattr__(self, "loaded_venues", venues)
