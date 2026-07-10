"""
====================================================
Vision Trading OS
Test Building Candle
====================================================
"""

from datetime import datetime

from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame

from core.models.building_candle import BuildingCandle


candle = BuildingCandle(
    symbol=Instrument.NIFTY,

    timeframe=TimeFrame.ONE_MINUTE,

    start_time=datetime.now(),

    end_time=datetime.now(),

    open=25200,

    high=25200,

    low=25200,

    close=25200,
)

print(candle)

print()

# simulate tick update

candle.high = 25220

candle.close = 25215

candle.volume += 100

print(candle)