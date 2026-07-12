"""
Tests for Zerodha market-data immutable models.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime

import pytest

from brokers.zerodha.market_data import (
    ZerodhaInstrumentSubscription,
    ZerodhaSubscriptionMode,
    ZerodhaTickBatchResult,
    ZerodhaWebSocketSnapshot,
    ZerodhaWebSocketStatus,
)
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.models.tick import Tick


def subscription(token=101, instrument=Instrument.NIFTY, mode=ZerodhaSubscriptionMode.FULL):
    return ZerodhaInstrumentSubscription(token, instrument, Exchange.NSE, mode)


def tick():
    return Tick(Instrument.NIFTY, Exchange.NSE, datetime(2026, 7, 12, tzinfo=UTC), 25000.0, 1, 24999.0, 25001.0, 0)


def test_valid_subscription_defaults_to_full_mode():
    item = subscription()

    assert item.instrument_token == 101
    assert item.instrument is Instrument.NIFTY
    assert item.exchange is Exchange.NSE
    assert item.mode is ZerodhaSubscriptionMode.FULL


def test_invalid_tokens_rejected():
    with pytest.raises(ValueError):
        subscription(0)


def test_boolean_tokens_rejected():
    with pytest.raises(TypeError):
        subscription(True)


def test_invalid_instrument_rejected():
    with pytest.raises(TypeError):
        ZerodhaInstrumentSubscription(101, "NIFTY", Exchange.NSE)


def test_invalid_exchange_rejected():
    with pytest.raises(TypeError):
        ZerodhaInstrumentSubscription(101, Instrument.NIFTY, "NSE")


def test_invalid_mode_rejected():
    with pytest.raises(TypeError):
        ZerodhaInstrumentSubscription(101, Instrument.NIFTY, Exchange.NSE, "full")


def test_snapshot_immutable_and_tuple_fields_immutable():
    snapshot = ZerodhaWebSocketSnapshot(
        status=ZerodhaWebSocketStatus.CREATED,
        connected=False,
        subscribed_instruments=[subscription()],
        connection_count=0,
        disconnection_count=0,
        reconnect_count=0,
        raw_tick_count=0,
        normalized_tick_count=0,
        delivered_tick_count=0,
        rejected_tick_count=0,
        last_connected_at=None,
        last_disconnected_at=None,
        last_tick_at=None,
        last_error=None,
    )

    assert isinstance(snapshot.subscribed_instruments, tuple)
    with pytest.raises(FrozenInstanceError):
        snapshot.connected = True


def test_batch_result_immutable_and_subset_validated():
    item = tick()
    batch = ZerodhaTickBatchResult(1, (item,), (item,), 0)

    with pytest.raises(FrozenInstanceError):
        batch.rejected_count = 1


def test_batch_result_rejects_delivered_tick_outside_normalized_set():
    first = tick()
    second = Tick(Instrument.BANKNIFTY, Exchange.NSE, first.timestamp, 50000.0, 1, 49999.0, 50001.0, 0)

    with pytest.raises(ValueError):
        ZerodhaTickBatchResult(1, (first,), (second,), 0)


def test_no_secret_fields_in_websocket_snapshot_model():
    names = {field.name for field in fields(ZerodhaWebSocketSnapshot)}

    assert "api_key" not in names
    assert "access_token" not in names
    assert "raw_tick" not in names
    assert "client" not in names
