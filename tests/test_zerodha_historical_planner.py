"""
Tests for Zerodha historical request planning.
"""

from datetime import UTC, datetime, timedelta

import pytest

from brokers.zerodha.historical import ZerodhaHistoricalRequest, ZerodhaHistoricalRequestPlanner
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def request(timeframe=TimeFrame.ONE_MINUTE, end=None):
    return ZerodhaHistoricalRequest(101, Instrument.NIFTY, Exchange.NSE, timeframe, NOW, end or NOW + timedelta(days=1))


def assert_contiguous(chunks):
    for left, right in zip(chunks, chunks[1:]):
        assert left.end_at == right.start_at
        assert left.end_at <= right.end_at


def test_small_large_boundaries_contiguous_no_overlap_no_gaps_and_deterministic():
    planner = ZerodhaHistoricalRequestPlanner()
    assert len(planner.plan(request())) == 1
    chunks = planner.plan(request(TimeFrame.ONE_MINUTE, NOW + timedelta(days=130)))
    assert len(chunks) == 3
    assert chunks[0].start_at == NOW
    assert chunks[-1].end_at == NOW + timedelta(days=130)
    assert_contiguous(chunks)
    assert chunks == planner.plan(request(TimeFrame.ONE_MINUTE, NOW + timedelta(days=130)))
    assert len(planner.plan(request(TimeFrame.FIVE_MINUTES, NOW + timedelta(days=250)))) == 3
    assert len(planner.plan(request(TimeFrame.DAILY, NOW + timedelta(days=2500)))) == 2


def test_weekly_monthly_rejected_and_no_network_sleep():
    planner = ZerodhaHistoricalRequestPlanner()
    for timeframe in (TimeFrame.WEEKLY, TimeFrame.MONTHLY):
        with pytest.raises(ValueError):
            planner.plan(request(timeframe, NOW + timedelta(days=10)))
    assert not hasattr(planner, "client")
    assert not hasattr(planner, "sleep")
