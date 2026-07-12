"""
Tests for live market-data dashboard presenters.
"""

from datetime import UTC, datetime

from application import ApplicationBootstrap
from application.live_market_data import LiveMarketDataRuntimeSnapshot, LiveMarketDataRuntimeStatus
from brokers.zerodha.market_data import (
    ZerodhaInstrumentSubscription,
    ZerodhaSubscriptionMode,
    ZerodhaWebSocketSnapshot,
    ZerodhaWebSocketStatus,
)
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from dashboard.presenters import build_dashboard_view, build_live_market_data_view


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def websocket(status=ZerodhaWebSocketStatus.CONNECTED, connected=True, subscriptions=None, error=None):
    return ZerodhaWebSocketSnapshot(
        status=status,
        connected=connected,
        subscribed_instruments=tuple(subscriptions or (sub(Instrument.NIFTY, 101),)),
        connection_count=2,
        disconnection_count=1,
        reconnect_count=3,
        raw_tick_count=4,
        normalized_tick_count=5,
        delivered_tick_count=6,
        rejected_tick_count=7,
        last_connected_at=NOW,
        last_disconnected_at=NOW,
        last_tick_at=NOW,
        last_error=error,
    )


def sub(instrument, token, mode=ZerodhaSubscriptionMode.FULL):
    exchange = Exchange.BSE if instrument is Instrument.SENSEX else Exchange.NSE
    return ZerodhaInstrumentSubscription(token, instrument, exchange, mode)


def snapshot(status=LiveMarketDataRuntimeStatus.RUNNING, ready=True, running=True, ws=None, error=None):
    return LiveMarketDataRuntimeSnapshot(
        status=status,
        ready=ready,
        running=running,
        configured_instruments=(Instrument.NIFTY, Instrument.SENSEX),
        configured_tokens=(101, 202),
        websocket=ws if ws is not None else websocket(subscriptions=(sub(Instrument.NIFTY, 101), sub(Instrument.SENSEX, 202, ZerodhaSubscriptionMode.QUOTE))),
        start_count=8,
        stop_count=9,
        last_started_at=NOW,
        last_stopped_at=NOW,
        last_error=error,
    )


def test_none_snapshot_produces_unavailable_view():
    view = build_live_market_data_view(None)
    assert view.available is False
    assert view.runtime_status == "Live market data not configured"
    assert view.subscription_rows == ()


def test_runtime_statuses_map_to_stable_text():
    cases = (
        (LiveMarketDataRuntimeStatus.CREATED, False, False, "Created"),
        (LiveMarketDataRuntimeStatus.READY, True, False, "Ready"),
        (LiveMarketDataRuntimeStatus.STARTING, True, False, "Starting"),
        (LiveMarketDataRuntimeStatus.RUNNING, True, True, "Running"),
        (LiveMarketDataRuntimeStatus.STOPPED, False, False, "Stopped"),
        (LiveMarketDataRuntimeStatus.ERROR, False, False, "Error"),
    )
    for status, ready, running, text in cases:
        view = build_live_market_data_view(snapshot(status, ready, running))
        assert view.runtime_status == text
        assert view.ready is ready
        assert view.running is running


def test_websocket_flags_counters_timestamps_and_error_map_without_mutation():
    source = snapshot(error="safe error")
    view = build_live_market_data_view(source)
    assert view.websocket_status == "Connected"
    assert view.connected is True
    assert view.connection_count == 2
    assert view.disconnection_count == 1
    assert view.reconnect_count == 3
    assert view.raw_tick_count == 4
    assert view.normalized_tick_count == 5
    assert view.delivered_tick_count == 6
    assert view.rejected_tick_count == 7
    assert view.start_count == 8
    assert view.stop_count == 9
    assert view.last_connected_at is NOW
    assert view.last_tick_at is NOW
    assert view.last_error == "safe error"
    assert source.configured_tokens == (101, 202)


def test_subscription_rows_preserve_order_and_human_readable_values():
    view = build_live_market_data_view(snapshot())
    assert [row.instrument for row in view.subscription_rows] == ["NIFTY", "SENSEX"]
    assert [row.exchange for row in view.subscription_rows] == ["NSE", "BSE"]
    assert [row.mode for row in view.subscription_rows] == ["Full", "Quote"]


def test_build_dashboard_view_supports_one_and_two_argument_calls_without_secrets():
    lifecycle = ApplicationBootstrap().create_application()
    one_arg = build_dashboard_view(lifecycle.snapshot())
    two_arg = build_dashboard_view(lifecycle.snapshot(), snapshot())
    assert one_arg.live_market_data.available is False
    assert two_arg.live_market_data.available is True
    assert "api_key" not in repr(two_arg.live_market_data)
    assert "access_token" not in repr(two_arg.live_market_data)
