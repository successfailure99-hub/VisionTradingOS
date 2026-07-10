"""
====================================================
Vision Trading OS
Test - Exchange Enum
====================================================
"""

from core.enums.exchange import Exchange


def test_supported_indian_exchanges():
    assert Exchange.NSE.value == "NSE"
    assert Exchange.BSE.value == "BSE"
    assert Exchange.MCX.value == "MCX"
    assert Exchange.NCDEX.value == "NCDEX"

    assert Exchange.NSE.is_indian
    assert Exchange.BSE.is_indian
    assert Exchange.MCX.is_indian
    assert Exchange.NCDEX.is_indian


def test_supported_international_exchanges():
    assert Exchange.CME.value == "CME"
    assert Exchange.NYSE.value == "NYSE"
    assert Exchange.NASDAQ.value == "NASDAQ"

    assert Exchange.CME.is_international
    assert Exchange.NYSE.is_international
    assert Exchange.NASDAQ.is_international


def test_exchange_from_value_normalizes_case_and_whitespace():
    assert Exchange.from_value(" nse ") is Exchange.NSE
    assert Exchange.from_value("nasdaq") is Exchange.NASDAQ


def test_exchange_from_value_rejects_unsupported_values():
    for value in ("NFO", "CDS"):
        try:
            Exchange.from_value(value)
        except ValueError:
            continue

        raise AssertionError(f"Expected {value} to be unsupported")
