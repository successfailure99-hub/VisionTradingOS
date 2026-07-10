"""
====================================================
Vision Trading OS
Test Tick Model
====================================================
"""

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