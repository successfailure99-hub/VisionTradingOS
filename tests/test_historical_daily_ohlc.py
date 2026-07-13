"""
Tests for historical DailyOHLC derivation.
"""

from datetime import UTC, datetime, timedelta

import pytest

from application.historical_warmup import derive_daily_ohlc
from core.enums.instrument import Instrument
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC


TS = datetime(2026, 7, 10, 9, 15, tzinfo=UTC)


def candle(offset=0, *, symbol="NIFTY", timeframe="1m", close=101.0):
    start = TS + timedelta(minutes=offset)
    return Candle(symbol, timeframe, start, start + timedelta(minutes=1), 100.0 + offset, 105.0 + offset, 95.0 - offset, close, 10)


def test_derives_open_high_low_close_sorted_and_deduplicated():
    result = derive_daily_ohlc((candle(2, close=120.0), candle(0), candle(1), candle(1)), instrument=Instrument.NIFTY)
    assert isinstance(result, DailyOHLC)
    assert result.open == 100.0
    assert result.high == 107.0
    assert result.low == 93.0
    assert result.close == 120.0


def test_rejects_conflicts_mixed_inputs_wrong_timeframe_naive_and_empty():
    with pytest.raises(ValueError):
        derive_daily_ohlc((candle(0), candle(0, close=102.0)), instrument=Instrument.NIFTY)
    with pytest.raises(ValueError):
        derive_daily_ohlc((candle(0), candle(1, symbol="BANKNIFTY")), instrument=Instrument.NIFTY)
    with pytest.raises(ValueError):
        derive_daily_ohlc((candle(0, timeframe="5m"),), instrument=Instrument.NIFTY)
    naive = Candle("NIFTY", "1m", datetime(2026, 7, 10, 9, 15), datetime(2026, 7, 10, 9, 16), 1, 2, 1, 1, 1)
    with pytest.raises(ValueError):
        derive_daily_ohlc((naive,), instrument=Instrument.NIFTY)
    with pytest.raises(ValueError):
        derive_daily_ohlc((), instrument=Instrument.NIFTY)
    with pytest.raises(ValueError):
        derive_daily_ohlc((candle(0), candle(0 + 24 * 60)), instrument=Instrument.NIFTY)
