from datetime import UTC, date, datetime

import pytest

from brokers.zerodha.options import ZerodhaOptionContractDiscoveryService, ZerodhaOptionDiscoveryStatus
from core.enums.instrument import Instrument


def raw(token, name="NIFTY", exchange="NFO", segment="NFO-OPT", right="CE", strike=25000):
    return dict(instrument_token=token, exchange_token=token + 1000, tradingsymbol=f"{name.replace(' ', '')}{token}{right}", name=name, exchange=exchange, segment=segment, instrument_type=right, expiry=date(2026, 7, 30), strike=strike, lot_size=75, tick_size=0.05)


class Client:
    def __init__(self, rows=None, fail=False):
        self.rows = rows or {}
        self.fail = fail
        self.calls = []

    def instruments(self, exchange=None):
        self.calls.append(exchange)
        if self.fail:
            raise RuntimeError("client failure {'access_token': 'secret'}")
        return self.rows.get(exchange, ())


def service(rows=None, fail=False):
    return ZerodhaOptionContractDiscoveryService(client=Client(rows, fail), clock=lambda: datetime(2026, 7, 10, 9, 15, tzinfo=UTC))


def test_constructor_no_load_default_and_targeted_load_counts_clear_and_resolver():
    rows = {
        "NFO": [raw(1), raw(2, right="PE"), raw(3, name="BANKNIFTY"), raw(4, name="RELIANCE")],
        "BFO": [raw(5, name="SENSEX", exchange="BFO", segment="BFO-OPT"), raw(6, name="SENSEX", exchange="BFO", segment="BFO-OPT", right="PE")],
    }
    item = service(rows)
    assert item.snapshot().status is ZerodhaOptionDiscoveryStatus.CREATED
    snapshot = item.load()
    assert item._client.calls == ["NFO", "BFO"]
    assert snapshot.status is ZerodhaOptionDiscoveryStatus.READY
    assert snapshot.record_count == 6
    assert snapshot.supported_contract_count == 5
    assert snapshot.available_underlyings == (Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX)
    assert snapshot.loaded_at.tzinfo is not None
    assert item.create_resolver()._catalogue is item.catalogue
    assert item.clear().status is ZerodhaOptionDiscoveryStatus.CLEARED
    nifty = service(rows)
    assert nifty.load((Instrument.NIFTY,)).loaded_venues[0].value == "NFO"
    assert nifty._client.calls == ["NFO"]
    assert service(rows).load((Instrument.SENSEX,)).loaded_venues[0].value == "BFO"


def test_load_rejects_bad_inputs_preserves_catalogue_and_errors_are_safe():
    item = service({"NFO": [raw(1), raw(2, right="PE")]})
    item.load((Instrument.NIFTY,))
    previous = item.catalogue.all()
    with pytest.raises(ValueError):
        item.load(())
    with pytest.raises(ValueError):
        item.load((Instrument.NIFTY, Instrument.NIFTY))
    with pytest.raises(ValueError):
        item.load((Instrument.FINNIFTY,))
    failing = service({"NFO": [raw(1, segment="BAD")]})
    with pytest.raises(ValueError):
        failing.load((Instrument.NIFTY,))
    assert failing.snapshot().status is ZerodhaOptionDiscoveryStatus.ERROR
    assert "{" not in failing.snapshot().last_error
    client_failure = ZerodhaOptionContractDiscoveryService(client=Client(fail=True), clock=lambda: datetime(2026, 7, 10, tzinfo=UTC))
    with pytest.raises(RuntimeError):
        client_failure.load((Instrument.NIFTY,))
    assert item.catalogue.all() == previous
    assert service({"NFO": []}).load((Instrument.NIFTY,)).status is ZerodhaOptionDiscoveryStatus.EMPTY
    with pytest.raises(ValueError):
        service({"NFO": [raw(1)], "BFO": [raw(1, name="SENSEX", exchange="BFO", segment="BFO-OPT")]}).load()
