"""
====================================================
Vision Trading OS
Test Tick Model
====================================================
"""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime

from core.enums.exchange import Exchange
from core.enums.instrument import Instrument

from core.models.tick import Tick


tick = Tick(
    symbol=Instrument.NIFTY,

    exchange=Exchange.NSE,

    timestamp=datetime.now(),

    last_price=25234.50,

    volume=1200000,

    bid_price=25234.45,

    ask_price=25234.55,

    open_interest=15400000,
)

print(tick)

print()

print("Instrument Value :", tick.symbol.value)

print("Exchange Value   :", tick.exchange.value)


def test_core_tick_model_preserves_supported_market_fields():
    assert tick.symbol is Instrument.NIFTY
    assert tick.exchange is Exchange.NSE
    assert tick.last_price == 25234.50
    assert tick.volume == 1200000
    assert tick.bid_price == 25234.45
    assert tick.ask_price == 25234.55
    assert tick.open_interest == 15400000


def test_core_tick_model_is_hashable_and_immutable():
    assert hash(tick) == hash(replace(tick))
    try:
        tick.last_price = 1.0
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("Tick must be immutable")
