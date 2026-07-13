"""
Tests for historical warm-up immutable models.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from application import ApplicationBootstrap
from application.historical_warmup import (
    HistoricalSeedResult,
    HistoricalWarmupInstrumentResult,
    HistoricalWarmupOperation,
    HistoricalWarmupRequest,
    HistoricalWarmupSnapshot,
    HistoricalWarmupStatus,
)
from brokers.zerodha.historical import ZerodhaHistoricalRequest, ZerodhaHistoricalResult
from brokers.zerodha.instruments import ZerodhaInstrumentRecord, ZerodhaInstrumentResolution, ZerodhaInstrumentType
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame


TS = datetime(2026, 7, 10, 9, 15, tzinfo=UTC)


def resolution():
    record = ZerodhaInstrumentRecord(101, 1, "NIFTY 50", "NIFTY 50", Exchange.NSE, "INDICES", ZerodhaInstrumentType.INDEX, None, 0.0, 1, 0.05)
    return ZerodhaInstrumentResolution(Instrument.NIFTY, record, ZerodhaInstrumentSubscription(101, Instrument.NIFTY, Exchange.NSE))


def historical_result():
    request = ZerodhaHistoricalRequest(101, Instrument.NIFTY, Exchange.NSE, TimeFrame.ONE_MINUTE, TS, TS + timedelta(minutes=1))
    return ZerodhaHistoricalResult(request, (), (), 0, 0, 0, 0, None, None, TS)


def runtime_snapshot():
    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    return lifecycle.orchestrator.snapshot().runtime_snapshots[0]


def test_seed_result_request_and_snapshot_are_frozen_and_validated():
    seed = HistoricalSeedResult(Instrument.NIFTY, 2, 1, 1, 0, TS, TS)
    assert seed.accepted_count == 1
    with pytest.raises(FrozenInstanceError):
        seed.accepted_count = 2
    with pytest.raises(ValueError):
        HistoricalSeedResult(Instrument.NIFTY, 1, 1, 1, 0, None, None)
    request = HistoricalWarmupRequest(resolution(), TS, TS + timedelta(minutes=1), HistoricalWarmupOperation.WARMUP)
    assert request.resolution.instrument is Instrument.NIFTY
    with pytest.raises(ValueError):
        HistoricalWarmupRequest(resolution(), TS, TS, HistoricalWarmupOperation.WARMUP)


def test_instrument_result_and_snapshot_contracts():
    seed = HistoricalSeedResult(Instrument.NIFTY, 0, 0, 0, 0, None, None)
    result = HistoricalWarmupInstrumentResult(Instrument.NIFTY, historical_result(), seed, None, runtime_snapshot(), 0, True, None)
    snapshot = HistoricalWarmupSnapshot(
        HistoricalWarmupStatus.READY,
        HistoricalWarmupOperation.WARMUP,
        (Instrument.NIFTY,),
        (Instrument.NIFTY,),
        (),
        (result,),
        1,
        1,
        0,
        0,
        0,
        TS,
        TS + timedelta(seconds=1),
        None,
    )
    assert snapshot.results == (result,)
    with pytest.raises(ValueError):
        HistoricalWarmupInstrumentResult(Instrument.NIFTY, historical_result(), seed, None, runtime_snapshot(), 0, False, None)
    with pytest.raises(ValueError):
        HistoricalWarmupSnapshot(HistoricalWarmupStatus.READY, None, (Instrument.NIFTY,), (Instrument.NIFTY,), (Instrument.NIFTY,), (), 0, 0, 0, 0, 0, None, None, None)
