"""
====================================================
Vision Trading OS
Test Candle
====================================================
"""

from datetime import datetime

from core.enums.timeframe import TimeFrame
from core.models.candle import Candle


candle = Candle(
    symbol="NIFTY",

    timeframe=TimeFrame.FIVE_MINUTE,

    start_time=datetime(2026, 7, 10, 9, 15),

    end_time=datetime(2026, 7, 10, 9, 20),

    open=25200,

    high=25232,

    low=25195,

    close=25228,

    volume=1250000,
)

print(candle)