"""
Tests for Zerodha historical series validator.
"""

from datetime import UTC, datetime, timedelta

import pytest

from brokers.zerodha.historical import HistoricalGapType, ZerodhaHistoricalSeriesValidator
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def candle(at, symbol="NIFTY", timeframe="5m", close=100.0):
    return Candle(symbol, timeframe, at, at + timedelta(minutes=5), 99.0, 101.0, 98.0, close, 10)


def test_ordering_duplicates_missing_gaps_and_immutability():
    validator = ZerodhaHistoricalSeriesValidator()
    ordered, gaps, duplicate_count = validator.validate((candle(NOW), candle(NOW + timedelta(minutes=5))), timeframe=TimeFrame.FIVE_MINUTES)
    assert [c.start_time for c in ordered] == [NOW, NOW + timedelta(minutes=5)]
    assert gaps == ()
    out, gaps, _ = validator.validate((candle(NOW + timedelta(minutes=5)), candle(NOW)), timeframe=TimeFrame.FIVE_MINUTES)
    assert [c.start_time for c in out] == [NOW, NOW + timedelta(minutes=5)]
    assert any(g.gap_type is HistoricalGapType.OUT_OF_ORDER for g in gaps)
    out, gaps, duplicate_count = validator.validate((candle(NOW), candle(NOW)), timeframe=TimeFrame.FIVE_MINUTES)
    assert len(out) == 1
    assert duplicate_count == 1
    assert any(g.gap_type is HistoricalGapType.DUPLICATE_TIMESTAMP for g in gaps)
    with pytest.raises(ValueError):
        validator.validate((candle(NOW), candle(NOW, close=100.5)), timeframe=TimeFrame.FIVE_MINUTES)
    _, gaps, _ = validator.validate((candle(NOW), candle(NOW + timedelta(minutes=15))), timeframe=TimeFrame.FIVE_MINUTES)
    missing = [g for g in gaps if g.gap_type is HistoricalGapType.MISSING_INTERVAL]
    assert missing[0].missing_intervals == 2


def test_overnight_daily_wrong_timeframe_mixed_symbols_and_empty():
    validator = ZerodhaHistoricalSeriesValidator()
    assert validator.validate((), timeframe=TimeFrame.FIVE_MINUTES) == ((), (), 0)
    overnight = (candle(NOW), candle(NOW + timedelta(days=1)))
    assert not any(g.gap_type is HistoricalGapType.MISSING_INTERVAL for g in validator.validate(overnight, timeframe=TimeFrame.FIVE_MINUTES)[1])
    daily = (Candle("NIFTY", "1D", NOW, NOW + timedelta(days=1), 1, 2, 1, 1, 1), Candle("NIFTY", "1D", NOW + timedelta(days=7), NOW + timedelta(days=8), 1, 2, 1, 1, 1))
    assert validator.validate(daily, timeframe=TimeFrame.DAILY)[1] == ()
    with pytest.raises(ValueError):
        validator.validate((candle(NOW, timeframe="1m"),), timeframe=TimeFrame.FIVE_MINUTES)
    with pytest.raises(ValueError):
        validator.validate((candle(NOW), candle(NOW + timedelta(minutes=5), symbol="BANKNIFTY")), timeframe=TimeFrame.FIVE_MINUTES)
    with pytest.raises(TypeError):
        validator.validate((object(),), timeframe=TimeFrame.FIVE_MINUTES)
