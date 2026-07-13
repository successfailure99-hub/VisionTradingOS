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
            try:
                raw_records: list[Mapping[str, object]] = []
                for venue in venues:
                    raw_records.extend(tuple(self._client.instruments(venue.value)))
                contracts = []
                for record in raw_records:
                    if is_candidate_record(record, underlyings, set(venues)):
                        contracts.append(self._normalizer.normalize(record))
                    elif _looks_like_requested_target(record, underlyings, set(venues)):
                        contracts.append(self._normalizer.normalize(record))
                self._catalogue.replace(tuple(contracts))
                self._record_count = len(raw_records)
                self._loaded_venues = venues
                self._loaded_at = require_aware(self._clock(), "clock result")
                self._status = ZerodhaOptionDiscoveryStatus.READY if contracts else ZerodhaOptionDiscoveryStatus.EMPTY
                return self._snapshot_unlocked()
            except Exception as exc:
                self._status = ZerodhaOptionDiscoveryStatus.ERROR
                self._last_error = _safe_error(exc)
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
            return self._snapshot_unlocked()

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


def _looks_like_requested_target(
    record: object,
    underlyings: tuple[Instrument, ...],
    venues: set[ZerodhaDerivativeVenue],
) -> bool:
    if not isinstance(record, Mapping):
        return False
    try:
        exchange = str(record.get("exchange", "")).strip().upper()
        instrument_type = str(record.get("instrument_type", "")).strip().upper()
        if ZerodhaDerivativeVenue(exchange) not in venues or instrument_type not in {"CE", "PE"}:
            return False
        return identify_underlying(record) in underlyings
    except Exception:
        name = str(record.get("name", "")).strip().upper()
        symbol = str(record.get("tradingsymbol", "")).strip().upper()
        roots = {Instrument.NIFTY: ("NIFTY",), Instrument.BANKNIFTY: ("BANKNIFTY", "NIFTY BANK"), Instrument.SENSEX: ("SENSEX",)}
        for underlying in underlyings:
            if name in roots[underlying] or any(symbol.startswith(root.replace(" ", "")) for root in roots[underlying]):
                return True
        return False


def _safe_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if "{" in message or "}" in message:
        return message.split("{", 1)[0].strip()
    return message
