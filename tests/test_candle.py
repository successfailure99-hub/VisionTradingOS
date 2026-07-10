"""
====================================================
Vision Trading OS
Test - Candle Model
====================================================
"""

from datetime import datetime

from core.enums.timeframe import TimeFrame
from core.models.candle import Candle


def test_candle_model_accepts_current_timeframe_value():
    candle = Candle(
        symbol="NIFTY",
        timeframe=TimeFrame.FIVE_MINUTES.value,
        start_time=datetime(2026, 7, 10, 9, 15),
        end_time=datetime(2026, 7, 10, 9, 20),
        open=25200,
        high=25232,
        low=25195,
        close=25228,
        volume=1250000,
    )

    assert candle.symbol == "NIFTY"
    assert candle.timeframe == "5m"
    assert candle.start_time == datetime(2026, 7, 10, 9, 15)
    assert candle.end_time == datetime(2026, 7, 10, 9, 20)
    assert candle.open == 25200
    assert candle.high == 25232
    assert candle.low == 25195
    assert candle.close == 25228
    assert candle.volume == 1250000
