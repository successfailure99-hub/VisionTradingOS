from datetime import date
from enum import IntEnum

import pytest

from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaOptionContractNormalizer, ZerodhaOptionRight
from core.enums.instrument import Instrument


def raw(**overrides):
    item = dict(
        instrument_token=1,
        exchange_token=11,
        tradingsymbol="NIFTY2673025000CE",
        name="NIFTY",
        exchange="NFO",
        segment="NFO-OPT",
        instrument_type="CE",
        expiry=date(2026, 7, 30),
        strike=25000,
        lot_size=75,
        tick_size=0.05,
    )
    item.update(overrides)
    return item


class IntegralToken(IntEnum):
    VALUE = 219258373


def test_normalizes_supported_underlyings_rights_and_name_symbol_rules():
    normalizer = ZerodhaOptionContractNormalizer()
    assert normalizer.normalize(raw()).right is ZerodhaOptionRight.CALL
    assert normalizer.normalize(raw(instrument_type="PE")).right is ZerodhaOptionRight.PUT
    assert normalizer.normalize(raw(name="BANKNIFTY", tradingsymbol="BANKNIFTY2673050000CE")).underlying is Instrument.BANKNIFTY
    assert normalizer.normalize(raw(name="NIFTY BANK", tradingsymbol="BANKNIFTY2673050000PE", instrument_type="PE")).underlying is Instrument.BANKNIFTY
    sensex = normalizer.normalize(raw(name="SENSEX", tradingsymbol="SENSEX2673080000CE", exchange="BFO", segment="BFO-OPT"))
    assert sensex.venue is ZerodhaDerivativeVenue.BFO
    blank_name = normalizer.normalize(raw(name="", tradingsymbol="BANKNIFTY2673050000CE"))
    assert blank_name.underlying is Instrument.BANKNIFTY
    assert blank_name.name == "BANKNIFTY"
    none_name = normalizer.normalize(raw(name=None, tradingsymbol="NIFTY2673025000CE"))
    assert none_name.underlying is Instrument.NIFTY
    assert none_name.name == "NIFTY"
    whitespace_name = normalizer.normalize(
        raw(
            name="   ",
            tradingsymbol="SENSEX2673080000CE",
            exchange="BFO",
            segment="BFO-OPT",
        )
    )
    assert whitespace_name.underlying is Instrument.SENSEX
    assert whitespace_name.name == "SENSEX"
    assert normalizer.normalize(raw(name="NIFTY", tradingsymbol="BANKNIFTY2673050000CE")).underlying is Instrument.NIFTY
    assert normalizer.normalize_many([raw(instrument_token=1), raw(instrument_token=2, instrument_type="PE")])[1].instrument_token == 2
    assert normalizer.normalize_many([]) == ()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("instrument_token", 219258373),
        ("instrument_token", "219258373"),
        ("instrument_token", IntegralToken.VALUE),
        ("exchange_token", 856478),
        ("exchange_token", "856478"),
        ("exchange_token", " 856478 "),
        ("lot_size", "20"),
    ),
)
def test_integral_master_fields_accept_safe_integer_representations(field, value):
    contract = ZerodhaOptionContractNormalizer().normalize(raw(**{field: value}))
    assert isinstance(getattr(contract, field), int)
    assert getattr(contract, field) == int(value)


@pytest.mark.parametrize(
    "overrides",
    [
        dict(exchange="NSE", segment="NSE"),
        dict(exchange="BSE", segment="BSE"),
        dict(instrument_type="FUT"),
        dict(instrument_type="EQ"),
        dict(name="RELIANCE", tradingsymbol="RELIANCE267302500CE"),
        dict(expiry=None),
        dict(strike=0),
        dict(exchange="BFO"),
        dict(segment="NFO-FUT"),
        dict(instrument_token=True),
        dict(exchange_token=None),
        dict(exchange_token=0),
        dict(exchange_token=True),
        dict(exchange_token=""),
        dict(exchange_token=" "),
        dict(exchange_token="-11"),
        dict(exchange_token="11.0"),
        dict(exchange_token="1e3"),
        dict(exchange_token=11.0),
        dict(exchange_token="bad"),
        dict(strike=float("nan")),
        dict(strike=float("inf")),
        dict(lot_size=None),
        dict(tick_size=None),
        dict(expiry="bad"),
    ],
)
def test_rejects_non_option_malformed_and_unsupported_records(overrides):
    with pytest.raises((TypeError, ValueError)):
        ZerodhaOptionContractNormalizer().normalize(raw(**overrides))


def test_rejects_substring_matches_and_does_not_mutate_raw_mapping():
    normalizer = ZerodhaOptionContractNormalizer()
    source = raw(name="OTHER NIFTY TEXT", tradingsymbol="OTHER2673025000CE")
    before = dict(source)
    with pytest.raises(ValueError):
        normalizer.normalize(source)
    assert source == before
    with pytest.raises(TypeError):
        normalizer.normalize("not a mapping")


def test_missing_exchange_token_is_rejected():
    item = raw()
    item.pop("exchange_token")
    with pytest.raises(TypeError):
        ZerodhaOptionContractNormalizer().normalize(item)


@pytest.mark.parametrize(
    "record",
    (
        raw(exchange="NFO", segment="NFO-OPT", instrument_type="CE", name="NIFTY", tradingsymbol="NIFTY2673025000CE", instrument_token="219258373", exchange_token="856478", lot_size="20"),
        raw(exchange="NFO", segment="NFO-OPT", instrument_type="PE", name="BANKNIFTY", tradingsymbol="BANKNIFTY2673050000PE", instrument_token="219258374", exchange_token="856479", lot_size="15"),
        raw(exchange="BFO", segment="BFO-OPT", instrument_type="CE", name="SENSEX", tradingsymbol="SENSEX2673080000CE", instrument_token="219258375", exchange_token="856480", lot_size="20"),
        raw(exchange="BFO", segment="BFO-OPT", instrument_type="PE", name="SENSEX", tradingsymbol="SENSEX2673080000PE", instrument_token=219258373, exchange_token="856478", lot_size=20, strike=26450.0),
    ),
)
def test_real_shaped_kite_option_records_with_numeric_strings_normalize(record):
    contract = ZerodhaOptionContractNormalizer().normalize(record)
    assert isinstance(contract.instrument_token, int)
    assert isinstance(contract.exchange_token, int)
    assert isinstance(contract.lot_size, int)
    assert contract.exchange_token > 0
