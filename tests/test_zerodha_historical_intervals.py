"""
Tests for Zerodha historical interval mapping.
"""

from datetime import timedelta

import pytest

from brokers.zerodha.historical import interval_duration, to_zerodha_interval
from core.enums.timeframe import TimeFrame


def test_all_v1_interval_mappings_and_durations():
    expected = {
        TimeFrame.ONE_MINUTE: ("minute", timedelta(minutes=1)),
        TimeFrame.THREE_MINUTES: ("3minute", timedelta(minutes=3)),
        TimeFrame.FIVE_MINUTES: ("5minute", timedelta(minutes=5)),
        TimeFrame.TEN_MINUTES: ("10minute", timedelta(minutes=10)),
        TimeFrame.FIFTEEN_MINUTES: ("15minute", timedelta(minutes=15)),
        TimeFrame.THIRTY_MINUTES: ("30minute", timedelta(minutes=30)),
        TimeFrame.ONE_HOUR: ("60minute", timedelta(hours=1)),
        TimeFrame.DAILY: ("day", timedelta(days=1)),
    }
    for timeframe, (interval, duration) in expected.items():
        assert to_zerodha_interval(timeframe) == interval
        assert interval_duration(timeframe) == duration


def test_weekly_monthly_and_invalid_values_rejected():
    for timeframe in (TimeFrame.WEEKLY, TimeFrame.MONTHLY):
        with pytest.raises(ValueError):
            to_zerodha_interval(timeframe)
        with pytest.raises(ValueError):
            interval_duration(timeframe)
    with pytest.raises(TypeError):
        to_zerodha_interval("5m")
