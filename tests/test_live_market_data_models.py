"""
Tests for live market-data immutable models.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime

import pytest

from application.enums import RuntimeInstrument, RuntimeStatus
from application.live_market_data import (
    LiveMarketDataDeliverySnapshot,
    LiveMarketDataRuntimeSnapshot,
    LiveMarketDataRuntimeStatus,
)
from application.models import RuntimeSnapshot
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 12, tzinfo=UTC)


def runtime_snapshot():
    return LiveMarketDataRuntimeSnapshot(
        status=LiveMarketDataRuntimeStatus.READY,
        ready=True,
        running=False,
        configured_instruments=(Instrument.NIFTY,),
        configured_tokens=(101,),
        websocket=None,
        start_count=0,
        stop_count=0,
        last_started_at=None,
        last_stopped_at=None,
        last_error=None,
    )


def app_runtime_snapshot():
    return RuntimeSnapshot(
        symbol=RuntimeInstrument.NIFTY,
        timeframe="1m",
        status=RuntimeStatus.RUNNING,
        latest_tick=None,
        latest_candle=None,
        vwap=None,
        cpr=None,
        camarilla=None,
        price_action=None,
        option_chain=None,
        market_context=None,
        ai_reasoning=None,
        strategy=None,
        risk=None,
        latest_order=None,
        position=None,
        latest_journal_record=None,
        updated_at=NOW,
    )


def test_runtime_snapshot_immutable_counts_timestamps_and_tuple_fields():
    snapshot = runtime_snapshot()

    assert snapshot.configured_instruments == (Instrument.NIFTY,)
    assert isinstance(snapshot.configured_tokens, tuple)
    with pytest.raises(FrozenInstanceError):
        snapshot.status = LiveMarketDataRuntimeStatus.ERROR
    with pytest.raises(ValueError):
        LiveMarketDataRuntimeSnapshot(LiveMarketDataRuntimeStatus.READY, True, True, (), (), None, 0, 0, None, None, None)
    with pytest.raises(ValueError):
        LiveMarketDataRuntimeSnapshot(LiveMarketDataRuntimeStatus.READY, True, False, (), (), None, -1, 0, None, None, None)
    with pytest.raises(ValueError):
        LiveMarketDataRuntimeSnapshot(LiveMarketDataRuntimeStatus.READY, True, False, (), (), None, 0, 0, datetime(2026, 7, 12), None, None)


def test_delivery_snapshot_rules_and_immutability():
    accepted = LiveMarketDataDeliverySnapshot(Instrument.NIFTY, True, app_runtime_snapshot(), None)
    failed = LiveMarketDataDeliverySnapshot(Instrument.NIFTY, False, None, "ValueError: stale")

    assert accepted.accepted is True
    assert failed.error
    with pytest.raises(FrozenInstanceError):
        accepted.accepted = False
    with pytest.raises(ValueError):
        LiveMarketDataDeliverySnapshot(Instrument.NIFTY, True, None, None)
    with pytest.raises(ValueError):
        LiveMarketDataDeliverySnapshot(Instrument.NIFTY, False, None, None)


def test_secret_fields_absent():
    names = {field.name for field in fields(LiveMarketDataRuntimeSnapshot)}

    assert "api_key" not in names
    assert "access_token" not in names
    assert "api_secret" not in names
    assert "session" not in names
