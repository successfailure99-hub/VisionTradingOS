"""
Deterministic index subscription resolver.
"""

from brokers.zerodha.instruments.catalogue import ZerodhaInstrumentCatalogue
from brokers.zerodha.instruments.enums import ZerodhaInstrumentType
from brokers.zerodha.instruments.models import ZerodhaInstrumentRecord, ZerodhaInstrumentResolution
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaSubscriptionMode
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


SUPPORTED_INDEXES = (Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX)

RULES = {
    Instrument.NIFTY: (
        Exchange.NSE,
        (("tradingsymbol", "NIFTY 50"), ("name", "NIFTY 50"), ("tradingsymbol", "NIFTY"), ("name", "NIFTY")),
    ),
    Instrument.BANKNIFTY: (
        Exchange.NSE,
        (("tradingsymbol", "NIFTY BANK"), ("name", "NIFTY BANK"), ("tradingsymbol", "BANKNIFTY"), ("name", "BANKNIFTY")),
    ),
    Instrument.SENSEX: (
        Exchange.BSE,
        (("tradingsymbol", "SENSEX"), ("name", "SENSEX"), ("tradingsymbol", "S&P BSE SENSEX"), ("name", "S&P BSE SENSEX")),
    ),
}


class ZerodhaIndexSubscriptionResolver:
    def __init__(
        self,
        catalogue: ZerodhaInstrumentCatalogue,
    ):
        if not isinstance(catalogue, ZerodhaInstrumentCatalogue):
            raise TypeError("catalogue must be ZerodhaInstrumentCatalogue")
        self._catalogue = catalogue

    def resolve(
        self,
        instrument: Instrument,
        *,
        mode: ZerodhaSubscriptionMode = ZerodhaSubscriptionMode.FULL,
    ) -> ZerodhaInstrumentResolution:
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be Instrument")
        if instrument not in SUPPORTED_INDEXES:
            raise ValueError(f"unsupported V1 instrument: {instrument.value}")
        if not isinstance(mode, ZerodhaSubscriptionMode):
            raise TypeError("mode must be ZerodhaSubscriptionMode")
        records = self._catalogue.all()
        if not records:
            raise ValueError("instrument catalogue is empty")
        record = self._resolve_record(instrument, records)
        subscription = ZerodhaInstrumentSubscription(
            instrument_token=record.instrument_token,
            instrument=instrument,
            exchange=record.exchange,
            mode=mode,
        )
        return ZerodhaInstrumentResolution(instrument, record, subscription)

    def resolve_many(
        self,
        instruments: tuple[Instrument, ...],
        *,
        mode: ZerodhaSubscriptionMode = ZerodhaSubscriptionMode.FULL,
    ) -> tuple[ZerodhaInstrumentResolution, ...]:
        requested = tuple(instruments)
        if len(set(requested)) != len(requested):
            raise ValueError("duplicate requested instruments")
        return tuple(self.resolve(instrument, mode=mode) for instrument in requested)

    def _resolve_record(
        self,
        instrument: Instrument,
        records: tuple[ZerodhaInstrumentRecord, ...],
    ) -> ZerodhaInstrumentRecord:
        exchange, aliases = RULES[instrument]
        candidates = tuple(
            record
            for record in records
            if record.exchange is exchange
            and record.instrument_type is ZerodhaInstrumentType.INDEX
            and record.expiry is None
        )
        for field_name, expected in aliases:
            matches = tuple(record for record in candidates if _key(getattr(record, field_name)) == _key(expected))
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise ValueError(f"ambiguous {instrument.value} instrument records")
        raise ValueError(f"no supported {instrument.value} instrument record found")


def _key(value: str) -> str:
    return value.strip().casefold()
