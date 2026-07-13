"""
Tests for Zerodha historical immutable models.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta

import pytest

from brokers.zerodha.historical import HistoricalGap, HistoricalGapType, ZerodhaHistoricalChunk, ZerodhaHistoricalRequest, ZerodhaHistoricalResult, ZerodhaHistoricalSnapshot, ZerodhaHistoricalStatus
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def request(**overrides):
    values = dict(instrument_token=101, instrument=Instrument.NIFTY, exchange=Exchange.NSE, timeframe=TimeFrame.FIVE_MINUTES, start_at=NOW, end_at=NOW + timedelta(minutes=5))
    values.update(overrides)
    return ZerodhaHistoricalRequest(**values)


def candle(at=NOW):
    return Candle("NIFTY", "5m", at, at + timedelta(minutes=5), 1.0, 2.0, 1.0, 1.5, 10)


def test_request_validation_and_immutability():
    item = request()
    assert item.instrument_token == 101
    with pytest.raises(FrozenInstanceError):
        item.instrument_token = 1
    for kwargs in (dict(instrument_token=0), dict(instrument_token=True), dict(instrument="NIFTY"), dict(exchange="NSE"), dict(timeframe="5m"), dict(start_at=datetime(2026, 1, 1)), dict(end_at=NOW), dict(continuous=True), dict(include_open_interest=True)):
        with pytest.raises((TypeError, ValueError)):
            request(**kwargs)


def test_chunk_gap_result_snapshot_validation_and_no_secret_fields():
    chunk = ZerodhaHistoricalChunk(NOW, NOW + timedelta(minutes=5))
    assert chunk.start_at == NOW
    with pytest.raises(ValueError):
        ZerodhaHistoricalChunk(NOW, NOW)
    gap = HistoricalGap(HistoricalGapType.MISSING_INTERVAL, NOW, NOW - timedelta(minutes=5), NOW + timedelta(minutes=5), 1)
    with pytest.raises(ValueError):
        HistoricalGap(HistoricalGapType.MISSING_INTERVAL, None, None, None, -1)
    result = ZerodhaHistoricalResult(request(), (candle(),), (gap,), 1, 1, 0, 0, NOW, NOW, NOW)
    with pytest.raises(FrozenInstanceError):
        result.normalized_count = 2
    with pytest.raises(ValueError):
        ZerodhaHistoricalResult(request(), (candle(),), (), 1, 2, 0, 0, NOW, NOW, NOW)
    snapshot = ZerodhaHistoricalSnapshot(ZerodhaHistoricalStatus.READY, 1, 1, 0, 1, 1, request(), result, NOW, NOW, None)
    with pytest.raises(FrozenInstanceError):
        snapshot.fetch_count = 2
    for cls in (ZerodhaHistoricalRequest, ZerodhaHistoricalResult, ZerodhaHistoricalSnapshot):
        names = {field.name for field in fields(cls)}
        assert names.isdisjoint({"api_key", "access_token", "api_secret", "request_token", "raw_records", "raw_payload", "session", "client"})
