"""
Tests for live market-data runtime configuration.
"""

from dataclasses import fields

import pytest

from application.live_market_data import LiveMarketDataConfiguration
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


def sub(token=101, instrument=Instrument.NIFTY):
    return ZerodhaInstrumentSubscription(token, instrument, Exchange.NSE)


def test_valid_configuration_normalizes_and_redacts_api_key():
    configuration = LiveMarketDataConfiguration("  api_key_1234  ", (sub(),))

    assert configuration.api_key == "api_key_1234"
    assert configuration.api_key_hint == "****1234"
    assert "api_key_1234" not in repr(configuration)
    assert "api_key_1234" not in str(configuration)
    assert configuration.auto_connect is False


def test_invalid_api_key_and_auto_connect_rejected():
    with pytest.raises(ValueError):
        LiveMarketDataConfiguration(" ", (sub(),))
    with pytest.raises(TypeError):
        LiveMarketDataConfiguration("api", (sub(),), auto_connect="yes")


def test_subscriptions_required_unique_ordered_and_tupled():
    first = sub(101, Instrument.NIFTY)
    second = sub(102, Instrument.BANKNIFTY)

    configuration = LiveMarketDataConfiguration("api", [first, second])

    assert configuration.subscriptions == (first, second)
    assert isinstance(configuration.subscriptions, tuple)
    with pytest.raises(ValueError):
        LiveMarketDataConfiguration("api", ())
    with pytest.raises(ValueError):
        LiveMarketDataConfiguration("api", (first, sub(101, Instrument.BANKNIFTY)))
    with pytest.raises(ValueError):
        LiveMarketDataConfiguration("api", (first, sub(102, Instrument.NIFTY)))


def test_no_secret_fields_or_hardcoded_token_requirement():
    names = {field.name for field in fields(LiveMarketDataConfiguration)}

    assert names == {"api_key", "subscriptions", "auto_connect"}
    assert "api_secret" not in names
    assert "access_token" not in names
    assert LiveMarketDataConfiguration("api", (sub(987654321),)).subscriptions[0].instrument_token == 987654321
