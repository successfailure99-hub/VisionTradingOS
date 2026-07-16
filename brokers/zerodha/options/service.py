"""
Explicit Zerodha option-contract discovery service.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from threading import RLock

from brokers.zerodha.instruments import ZerodhaInstrumentClientProtocol
from brokers.zerodha.options.catalogue import ZerodhaOptionContractCatalogue
from brokers.zerodha.options.contract_resolver import ZerodhaOptionContractResolver
from brokers.zerodha.options.enums import ZerodhaDerivativeVenue, ZerodhaOptionDiscoveryStatus
from brokers.zerodha.options.models import (
    SUPPORTED_UNDERLYINGS,
    ZerodhaOptionDiscoverySnapshot,
    require_aware,
    require_supported_underlying,
    venue_for_underlying,
)
from brokers.zerodha.options.normalizer import ZerodhaOptionContractNormalizer, identify_underlying, is_candidate_record
from core.enums.instrument import Instrument


class ZerodhaOptionContractDiscoveryService:
    def __init__(
        self,
        *,
        client: ZerodhaInstrumentClientProtocol,
        normalizer: ZerodhaOptionContractNormalizer | None = None,
        catalogue: ZerodhaOptionContractCatalogue | None = None,
        clock=None,
    ):
        if not hasattr(client, "instruments"):
            raise TypeError("client must implement instruments")
        self._client = client
        self._normalizer = normalizer or ZerodhaOptionContractNormalizer()
        if not isinstance(self._normalizer, ZerodhaOptionContractNormalizer):
            raise TypeError("normalizer must be ZerodhaOptionContractNormalizer")
        self._catalogue = catalogue or ZerodhaOptionContractCatalogue()
        if not isinstance(self._catalogue, ZerodhaOptionContractCatalogue):
            raise TypeError("catalogue must be ZerodhaOptionContractCatalogue")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = RLock()
        self._status = ZerodhaOptionDiscoveryStatus.CREATED
        self._record_count = 0
        self._loaded_venues: tuple[ZerodhaDerivativeVenue, ...] = ()
        self._loaded_at: datetime | None = None
        self._last_error: str | None = None
        self._rejected_contracts: tuple[str, ...] = ()
        self._rejections_by_underlying: dict[Instrument, tuple[str, ...]] = {}
        self._accepted_by_underlying: dict[Instrument, int] = {}

    @property
    def catalogue(self) -> ZerodhaOptionContractCatalogue:
        return self._catalogue

    def load(
        self,
        underlyings: tuple[Instrument, ...] = SUPPORTED_UNDERLYINGS,
    ) -> ZerodhaOptionDiscoverySnapshot:
        underlyings = self._validate_underlyings(underlyings)
        venues = tuple(dict.fromkeys(venue_for_underlying(underlying) for underlying in underlyings))
        with self._lock:
            self._status = ZerodhaOptionDiscoveryStatus.LOADING
            self._last_error = None
            self._rejections_by_underlying = {}
            self._accepted_by_underlying = {}
            try:
                raw_records: list[Mapping[str, object]] = []
                for venue in venues:
                    raw_records.extend(tuple(self._client.instruments(venue.value)))
                contracts = []
                rejections = []
                rejected_by_underlying: dict[Instrument, list[str]] = {underlying: [] for underlying in underlyings}
                accepted_by_underlying: dict[Instrument, int] = {underlying: 0 for underlying in underlyings}
                for record in raw_records:
                    underlying = _record_underlying(record, underlyings, set(venues))
                    if underlying is None:
                        continue
                    try:
                        contract = self._normalizer.normalize(record)
                        contracts.append(contract)
                        accepted_by_underlying[contract.underlying] = accepted_by_underlying.get(contract.underlying, 0) + 1
                    except (TypeError, ValueError) as exc:
                        message = _rejected_contract_message(record, exc)
                        rejections.append(message)
                        rejected_by_underlying.setdefault(underlying, []).append(message)
                self._catalogue.replace(tuple(contracts))
                self._record_count = len(raw_records)
                self._loaded_venues = venues
                self._loaded_at = require_aware(self._clock(), "clock result")
                self._status = ZerodhaOptionDiscoveryStatus.READY if contracts else ZerodhaOptionDiscoveryStatus.EMPTY
                self._rejected_contracts = tuple(rejections)
                self._rejections_by_underlying = {
                    underlying: tuple(values)
                    for underlying, values in rejected_by_underlying.items()
                    if values
                }
                self._accepted_by_underlying = accepted_by_underlying
                self._last_error = _discovery_message(self._status, self._rejected_contracts)
                return self._snapshot_unlocked()
            except Exception as exc:
                self._status = ZerodhaOptionDiscoveryStatus.ERROR
                self._last_error = f"Discovery Failed: {_safe_error(exc)}"
                raise

    def create_resolver(self) -> ZerodhaOptionContractResolver:
        return ZerodhaOptionContractResolver(self._catalogue, clock=self._clock)

    def snapshot(self) -> ZerodhaOptionDiscoverySnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def clear(self) -> ZerodhaOptionDiscoverySnapshot:
        with self._lock:
            self._catalogue.clear()
            self._status = ZerodhaOptionDiscoveryStatus.CLEARED
            self._record_count = 0
            self._loaded_venues = ()
            self._loaded_at = None
            self._last_error = None
            self._rejected_contracts = ()
            self._rejections_by_underlying = {}
            self._accepted_by_underlying = {}
            return self._snapshot_unlocked()

    def accepted_count(self, underlying: Instrument) -> int:
        require_supported_underlying(underlying)
        with self._lock:
            return self._accepted_by_underlying.get(underlying, 0)

    def rejected_count(self, underlying: Instrument) -> int:
        require_supported_underlying(underlying)
        with self._lock:
            return len(self._rejections_by_underlying.get(underlying, ()))

    def rejection_examples(self, underlying: Instrument, *, limit: int = 3) -> tuple[str, ...]:
        require_supported_underlying(underlying)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        with self._lock:
            return self._rejections_by_underlying.get(underlying, ())[:limit]

    def error_for(self, underlying: Instrument) -> str | None:
        require_supported_underlying(underlying)
        with self._lock:
            accepted = self._accepted_by_underlying.get(underlying, 0)
            rejected = len(self._rejections_by_underlying.get(underlying, ()))
            if accepted > 0:
                return None
            if rejected > 0:
                return f"No valid {underlying.value} contracts were discovered."
            if self._status in {ZerodhaOptionDiscoveryStatus.EMPTY, ZerodhaOptionDiscoveryStatus.READY}:
                return f"No valid {underlying.value} contracts were discovered."
            return self._last_error

    def _snapshot_unlocked(self) -> ZerodhaOptionDiscoverySnapshot:
        contracts = self._catalogue.all()
        available = tuple(underlying for underlying in SUPPORTED_UNDERLYINGS if any(contract.underlying is underlying for contract in contracts))
        expiry_count = len({(contract.underlying, contract.expiry) for contract in contracts})
        return ZerodhaOptionDiscoverySnapshot(
            status=self._status,
            record_count=self._record_count,
            supported_contract_count=len(contracts),
            available_underlyings=available,
            available_expiry_count=expiry_count,
            loaded_venues=self._loaded_venues,
            loaded_at=self._loaded_at,
            last_error=self._last_error,
        )

    def _validate_underlyings(self, underlyings: tuple[Instrument, ...]) -> tuple[Instrument, ...]:
        values = tuple(underlyings)
        if not values:
            raise ValueError("at least one underlying is required")
        if len(set(values)) != len(values):
            raise ValueError("duplicate underlying")
        for underlying in values:
            require_supported_underlying(underlying)
        return values


def _is_requested_option_record(
    record: object,
    underlyings: tuple[Instrument, ...],
    venues: set[ZerodhaDerivativeVenue],
) -> bool:
    if not isinstance(record, Mapping):
        return False
    if is_candidate_record(record, underlyings, venues):
        return True
    exchange = str(record.get("exchange", "")).strip().upper()
    segment = str(record.get("segment", "")).strip().upper()
    instrument_type = str(record.get("instrument_type", "")).strip().upper()
    try:
        venue = ZerodhaDerivativeVenue(exchange)
    except ValueError:
        return False
    if venue not in venues or segment != f"{venue.value}-OPT" or instrument_type not in {"CE", "PE"}:
        return False
    name = str(record.get("name", "")).strip().upper()
    symbol = str(record.get("tradingsymbol", "")).strip().upper()
    roots = {Instrument.NIFTY: ("NIFTY",), Instrument.BANKNIFTY: ("BANKNIFTY", "NIFTY BANK"), Instrument.SENSEX: ("SENSEX",)}
    for underlying in underlyings:
        if name in roots[underlying] or any(symbol.startswith(root.replace(" ", "")) for root in roots[underlying]):
            return True
    return False


def _record_underlying(
    record: object,
    underlyings: tuple[Instrument, ...],
    venues: set[ZerodhaDerivativeVenue],
) -> Instrument | None:
    if not isinstance(record, Mapping):
        return None
    if not _matches_requested_option_shape(record, venues):
        return None
    try:
        underlying = identify_underlying(record)
    except Exception:
        underlying = _fallback_underlying(record, underlyings)
    if underlying in underlyings:
        return underlying
    return None


def _matches_requested_option_shape(record: Mapping[str, object], venues: set[ZerodhaDerivativeVenue]) -> bool:
    exchange = str(record.get("exchange", "")).strip().upper()
    segment = str(record.get("segment", "")).strip().upper()
    instrument_type = str(record.get("instrument_type", "")).strip().upper()
    try:
        venue = ZerodhaDerivativeVenue(exchange)
    except ValueError:
        return False
    return venue in venues and segment == f"{venue.value}-OPT" and instrument_type in {"CE", "PE"}


def _fallback_underlying(record: Mapping[str, object], underlyings: tuple[Instrument, ...]) -> Instrument | None:
    name = str(record.get("name", "")).strip().upper()
    symbol = str(record.get("tradingsymbol", "")).strip().upper()
    roots = {Instrument.NIFTY: ("NIFTY",), Instrument.BANKNIFTY: ("BANKNIFTY", "NIFTY BANK"), Instrument.SENSEX: ("SENSEX",)}
    for underlying in underlyings:
        if name in roots[underlying] or any(symbol.startswith(root.replace(" ", "")) for root in roots[underlying]):
            return underlying
    return None


def _rejected_contract_message(record: Mapping[str, object], exc: Exception) -> str:
    return (
        "Rejected contract: "
        f"reason={exc}; "
        f"tradingsymbol={_safe_field(record.get('tradingsymbol'))}; "
        f"instrument_token={_safe_field(record.get('instrument_token'))}; "
        f"exchange_token={_safe_field(record.get('exchange_token'))}"
    )


def _safe_field(value: object) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    if not text:
        return "-"
    if "{" in text or "}" in text:
        return text.split("{", 1)[0].strip()
    return text


def _discovery_message(status: ZerodhaOptionDiscoveryStatus, rejections: tuple[str, ...]) -> str | None:
    if status is ZerodhaOptionDiscoveryStatus.EMPTY:
        if rejections:
            return "No Valid Contracts: " + " | ".join(rejections[-3:])
        return "No Contracts Found"
    if rejections:
        return " | ".join(rejections[-3:])
    return None


def _safe_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if "{" in message or "}" in message:
        return message.split("{", 1)[0].strip()
    return message
