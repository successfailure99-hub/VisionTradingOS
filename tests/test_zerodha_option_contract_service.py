from datetime import UTC, date, datetime

import pytest

from brokers.zerodha.options import ZerodhaOptionContractDiscoveryService, ZerodhaOptionDiscoveryStatus
from core.enums.instrument import Instrument


DEFAULT_EXCHANGE_TOKEN = object()


def raw(token, name="NIFTY", exchange="NFO", segment="NFO-OPT", right="CE", strike=25000, exchange_token=DEFAULT_EXCHANGE_TOKEN):
    return dict(instrument_token=token, exchange_token=token + 1000 if exchange_token is DEFAULT_EXCHANGE_TOKEN else exchange_token, tradingsymbol=f"{name.replace(' ', '')}{token}{right}", name=name, exchange=exchange, segment=segment, instrument_type=right, expiry=date(2026, 7, 30), strike=strike, lot_size=75, tick_size=0.05)


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
    empty = service({"NFO": [raw(1, segment="BAD")]})
    empty_snapshot = empty.load((Instrument.NIFTY,))
    assert empty_snapshot.status is ZerodhaOptionDiscoveryStatus.EMPTY
    assert empty_snapshot.last_error == "No Contracts Found"
    client_failure = ZerodhaOptionContractDiscoveryService(client=Client(fail=True), clock=lambda: datetime(2026, 7, 10, tzinfo=UTC))
    with pytest.raises(RuntimeError):
        client_failure.load((Instrument.NIFTY,))
    assert item.catalogue.all() == previous
    assert service({"NFO": []}).load((Instrument.NIFTY,)).status is ZerodhaOptionDiscoveryStatus.EMPTY
    with pytest.raises(ValueError):
        service({"NFO": [raw(1)], "BFO": [raw(1, name="SENSEX", exchange="BFO", segment="BFO-OPT")]}).load()


@pytest.mark.parametrize(
    "record",
    (
        raw(1, exchange_token=None),
        raw(1, exchange_token=0),
        raw(1, exchange_token="1001.0"),
        {key: value for key, value in raw(1).items() if key != "exchange_token"},
    ),
)
def test_invalid_exchange_tokens_are_rejected_without_crashing_discovery(record):
    item = service({"NFO": [record]})
    snapshot = item.load((Instrument.NIFTY,))
    assert snapshot.status is ZerodhaOptionDiscoveryStatus.EMPTY
    assert snapshot.supported_contract_count == 0
    assert snapshot.last_error.startswith("No Valid Contracts: Rejected contract:")
    assert "exchange_token" in snapshot.last_error
    assert item.catalogue.all() == ()


def test_mixed_valid_invalid_contracts_continue_and_subscriptions_use_valid_tokens_only():
    rows = {
        "NFO": [
            raw(1, right="CE", strike=25000),
            raw(2, right="PE", strike=25000),
            raw(3, right="CE", strike=25100),
            raw(4, right="PE", strike=25100),
            raw(5, right="CE", strike=25200, exchange_token=0),
            raw(6, right="PE", strike=25200, exchange_token="1006.0"),
            raw(7, right="CE", strike=25300, segment="NFO-FUT"),
            raw(8, right="PE", strike=25300, segment="NFO-OPT", exchange="NSE"),
        ]
    }
    item = service(rows)
    snapshot = item.load((Instrument.NIFTY,))
    assert snapshot.status is ZerodhaOptionDiscoveryStatus.READY
    assert snapshot.supported_contract_count == 4
    assert snapshot.last_error is not None
    assert "Rejected contract:" in snapshot.last_error
    assert item.accepted_count(Instrument.NIFTY) == 4
    assert item.rejected_count(Instrument.NIFTY) == 2
    assert len(item.rejection_examples(Instrument.NIFTY)) == 2
    contracts = item.catalogue.all()
    assert tuple(contract.instrument_token for contract in contracts) == (1, 2, 3, 4)
    assert tuple(contract.exchange_token for contract in contracts) == (1001, 1002, 1003, 1004)
    universe = item.create_resolver().resolve_universe(
        Instrument.NIFTY,
        as_of=date(2026, 7, 1),
        underlying_price=25000,
        strikes_each_side=0,
    )
    assert tuple(subscription.instrument_token for subscription in universe.subscriptions) == (1, 2)


def test_invalid_sensex_contracts_do_not_block_nifty_or_banknifty_discovery():
    rows = {
        "NFO": [
            raw(1, name="NIFTY", right="CE", strike=25000),
            raw(2, name="NIFTY", right="PE", strike=25000),
            raw(3, name="NIFTY", right="CE", strike=25100),
            raw(4, name="NIFTY", right="PE", strike=25100),
            raw(5, name="BANKNIFTY", right="CE", strike=52000),
            raw(6, name="BANKNIFTY", right="PE", strike=52000),
            raw(7, name="BANKNIFTY", right="CE", strike=52100),
            raw(8, name="BANKNIFTY", right="PE", strike=52100),
        ],
        "BFO": [
            raw(9, name="SENSEX", exchange="BFO", segment="BFO-OPT", right="CE", strike=81000, exchange_token=0),
            raw(10, name="SENSEX", exchange="BFO", segment="BFO-OPT", right="PE", strike=81000, exchange_token=None),
        ],
    }
    item = service(rows)
    snapshot = item.load((Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX))
    assert snapshot.status is ZerodhaOptionDiscoveryStatus.READY
    assert snapshot.available_underlyings == (Instrument.NIFTY, Instrument.BANKNIFTY)
    assert "Rejected contract:" in snapshot.last_error
    assert item.accepted_count(Instrument.NIFTY) == 4
    assert item.accepted_count(Instrument.BANKNIFTY) == 4
    assert item.accepted_count(Instrument.SENSEX) == 0
    assert item.rejected_count(Instrument.SENSEX) == 2
    assert item.error_for(Instrument.NIFTY) is None
    assert item.error_for(Instrument.BANKNIFTY) is None
    assert item.error_for(Instrument.SENSEX) == "No valid SENSEX contracts were discovered."
    resolver = item.create_resolver()
    nifty = resolver.resolve_universe(Instrument.NIFTY, as_of=date(2026, 7, 1), underlying_price=25000, strikes_each_side=0)
    banknifty = resolver.resolve_universe(Instrument.BANKNIFTY, as_of=date(2026, 7, 1), underlying_price=52000, strikes_each_side=0)
    assert tuple(subscription.instrument_token for subscription in nifty.subscriptions) == (1, 2)
    assert tuple(subscription.instrument_token for subscription in banknifty.subscriptions) == (5, 6)
