"""
Zerodha instrument discovery service.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from threading import RLock

from application.live_market_data import LiveMarketDataConfiguration
from brokers.zerodha.instruments.catalogue import ZerodhaInstrumentCatalogue
from brokers.zerodha.instruments.client import ZerodhaInstrumentClientProtocol
from brokers.zerodha.instruments.enums import ZerodhaInstrumentDiscoveryStatus, ZerodhaInstrumentType
from brokers.zerodha.instruments.models import ZerodhaInstrumentDiscoverySnapshot, ZerodhaInstrumentRecord, ZerodhaInstrumentResolution
from brokers.zerodha.instruments.normalizer import ZerodhaInstrumentNormalizer
from brokers.zerodha.instruments.resolver import SUPPORTED_INDEXES, ZerodhaIndexSubscriptionResolver
from core.enums.exchange import Exchange


SUPPORTED_DISCOVERY_EXCHANGES = (Exchange.NSE, Exchange.BSE)


def _default_clock() -> datetime:
    return datetime.now(UTC)


class ZerodhaInstrumentDiscoveryService:
    def __init__(
        self,
        *,
        client: ZerodhaInstrumentClientProtocol,
        normalizer: ZerodhaInstrumentNormalizer | None = None,
        catalogue: ZerodhaInstrumentCatalogue | None = None,
        clock=None,
    ):
        if not hasattr(client, "instruments") or not callable(client.instruments):
            raise TypeError("client must expose instruments")
        if normalizer is not None and not isinstance(normalizer, ZerodhaInstrumentNormalizer):
            raise TypeError("normalizer must be ZerodhaInstrumentNormalizer")
        if catalogue is not None and not isinstance(catalogue, ZerodhaInstrumentCatalogue):
            raise TypeError("catalogue must be ZerodhaInstrumentCatalogue")
        self._client = client
        self._normalizer = normalizer or ZerodhaInstrumentNormalizer()
        self._catalogue = catalogue or ZerodhaInstrumentCatalogue()
        self._clock = clock or _default_clock
        self._lock = RLock()
        self._status = ZerodhaInstrumentDiscoveryStatus.CREATED
        self._loaded_exchanges: tuple[Exchange, ...] = ()
        self._loaded_at: datetime | None = None
        self._last_error: str | None = None

    @property
    def catalogue(self) -> ZerodhaInstrumentCatalogue:
        return self._catalogue

    def load(
        self,
        exchanges: tuple[Exchange, ...] = (
            Exchange.NSE,
            Exchange.BSE,
        ),
    ) -> ZerodhaInstrumentDiscoverySnapshot:
        requested = _validate_exchanges(exchanges)
        with self._lock:
            self._status = ZerodhaInstrumentDiscoveryStatus.LOADING
            try:
                records = self._load_records(requested)
                self._catalogue.replace(records)
                self._status = ZerodhaInstrumentDiscoveryStatus.READY
                self._loaded_exchanges = requested
                self._loaded_at = self._now()
                self._last_error = None
            except Exception as exc:
                self._status = ZerodhaInstrumentDiscoveryStatus.ERROR
                self._last_error = _safe_error(exc)
                raise
            return self._snapshot_unlocked()

    def clear(self) -> ZerodhaInstrumentDiscoverySnapshot:
        with self._lock:
            self._catalogue.clear()
            self._status = ZerodhaInstrumentDiscoveryStatus.CLEARED
            self._loaded_exchanges = ()
            self._loaded_at = None
            self._last_error = None
            return self._snapshot_unlocked()

    def snapshot(self) -> ZerodhaInstrumentDiscoverySnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def create_resolver(self) -> ZerodhaIndexSubscriptionResolver:
        return ZerodhaIndexSubscriptionResolver(self._catalogue)

    def _load_records(self, exchanges: tuple[Exchange, ...]) -> tuple[ZerodhaInstrumentRecord, ...]:
        loaded: list[ZerodhaInstrumentRecord] = []
        for exchange in exchanges:
            raw_records = self._client.instruments(exchange.value)
            if isinstance(raw_records, (str, bytes)) or not isinstance(raw_records, Sequence):
                raise TypeError("client instruments response must be a sequence")
            records = self._normalizer.normalize_many(raw_records)
            for record in records:
                if record.exchange is not exchange:
                    raise ValueError("normalized record exchange does not match requested exchange")
            loaded.extend(records)
        tokens = [record.instrument_token for record in loaded]
        if len(tokens) != len(set(tokens)):
            raise ValueError("duplicate instrument token across exchanges")
        return tuple(loaded)

    def _snapshot_unlocked(self) -> ZerodhaInstrumentDiscoverySnapshot:
        records = self._catalogue.all()
        return ZerodhaInstrumentDiscoverySnapshot(
            status=self._status,
            record_count=len(records),
            index_record_count=sum(1 for record in records if record.instrument_type is ZerodhaInstrumentType.INDEX),
            supported_resolution_count=self._supported_resolution_count(),
            loaded_exchanges=self._loaded_exchanges,
            loaded_at=self._loaded_at,
            last_error=self._last_error,
        )

    def _supported_resolution_count(self) -> int:
        resolver = self.create_resolver()
        count = 0
        for instrument in SUPPORTED_INDEXES:
            try:
                resolver.resolve(instrument)
            except Exception:
                continue
            count += 1
        return count

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock result must be datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock result must be timezone-aware")
        return value


def build_live_market_data_configuration(
    *,
    api_key: str,
    resolutions: tuple[ZerodhaInstrumentResolution, ...],
    auto_connect: bool = False,
) -> LiveMarketDataConfiguration:
    normalized = tuple(resolutions)
    if not normalized:
        raise ValueError("at least one resolution is required")
    if any(not isinstance(resolution, ZerodhaInstrumentResolution) for resolution in normalized):
        raise TypeError("resolutions must contain ZerodhaInstrumentResolution values")
    instruments = [resolution.instrument for resolution in normalized]
    tokens = [resolution.subscription.instrument_token for resolution in normalized]
    if len(instruments) != len(set(instruments)):
        raise ValueError("duplicate instruments")
    if len(tokens) != len(set(tokens)):
        raise ValueError("duplicate instrument tokens")
    return LiveMarketDataConfiguration(
        api_key=api_key,
        subscriptions=tuple(resolution.subscription for resolution in normalized),
        auto_connect=auto_connect,
    )


def _validate_exchanges(exchanges: tuple[Exchange, ...]) -> tuple[Exchange, ...]:
    requested = tuple(exchanges)
    if not requested:
        raise ValueError("at least one exchange is required")
    if any(not isinstance(exchange, Exchange) for exchange in requested):
        raise TypeError("exchanges must contain Exchange values")
    if len(requested) != len(set(requested)):
        raise ValueError("duplicate exchanges")
    unsupported = tuple(exchange for exchange in requested if exchange not in SUPPORTED_DISCOVERY_EXCHANGES)
    if unsupported:
        raise ValueError("unsupported discovery exchange")
    return requested


def _safe_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if "{" in message or "}" in message:
        return message.split("{", 1)[0].strip()
    return message
