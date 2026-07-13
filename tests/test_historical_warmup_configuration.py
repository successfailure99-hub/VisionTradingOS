"""
Tests for historical warm-up configuration.
"""

from dataclasses import FrozenInstanceError

import pytest

from application.historical_warmup import HistoricalWarmupConfiguration
from core.enums.timeframe import TimeFrame


def test_default_configuration_is_one_minute_frozen_and_has_no_credentials():
    config = HistoricalWarmupConfiguration()
    assert config.timeframe is TimeFrame.ONE_MINUTE
    assert config.warmup_candle_count == 375
    assert config.derive_previous_daily_ohlc is True
    assert config.strict_gap_validation is False
    assert not hasattr(config, "api_key")
    assert not hasattr(config, "access_token")
    with pytest.raises(FrozenInstanceError):
        config.warmup_candle_count = 1


def test_rejects_non_v1_timeframes_counts_and_booleans():
    with pytest.raises(ValueError):
        HistoricalWarmupConfiguration(timeframe=TimeFrame.FIVE_MINUTES)
    with pytest.raises(TypeError):
        HistoricalWarmupConfiguration(warmup_candle_count=True)
    with pytest.raises(ValueError):
        HistoricalWarmupConfiguration(warmup_candle_count=0)
    with pytest.raises(TypeError):
        HistoricalWarmupConfiguration(derive_previous_daily_ohlc="yes")
    with pytest.raises(TypeError):
        HistoricalWarmupConfiguration(strict_gap_validation=1)
