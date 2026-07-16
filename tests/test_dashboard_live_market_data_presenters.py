"""
Tests for live market-data dashboard presenters.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

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
IST = ZoneInfo("Asia/Kolkata")


def ist_clock(year=2026, month=7, day=13, hour=9, minute=15):
    return lambda: datetime(year, month, day, hour, minute, tzinfo=IST)


def websocket(
    status=ZerodhaWebSocketStatus.CONNECTED,
    connected=True,
    subscriptions=None,
    error=None,
    delivered_tick_count=6,
    last_tick_at=NOW,
):
    return ZerodhaWebSocketSnapshot(
        status=status,
        connected=connected,
        subscribed_instruments=tuple(subscriptions or (sub(Instrument.NIFTY, 101),)),
        connection_count=2,
        disconnection_count=1,
        reconnect_count=3,
        raw_tick_count=4,
        normalized_tick_count=5,
        delivered_tick_count=delivered_tick_count,
        rejected_tick_count=7,
        last_connected_at=NOW,
        last_disconnected_at=NOW,
        last_tick_at=last_tick_at,
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
        view = build_live_market_data_view(snapshot(status, ready, running), clock=ist_clock())
        assert view.runtime_status == text
        assert view.ready is ready
        assert view.running is running


def test_websocket_flags_counters_timestamps_and_error_map_without_mutation():
    source = snapshot(error="safe error")
    view = build_live_market_data_view(source, clock=ist_clock())
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
    view = build_live_market_data_view(snapshot(), clock=ist_clock())
    assert [row.instrument for row in view.subscription_rows] == ["NIFTY", "SENSEX"]
    assert [row.exchange for row in view.subscription_rows] == ["NSE", "BSE"]
    assert [row.mode for row in view.subscription_rows] == ["Full", "Quote"]


def test_build_dashboard_view_supports_one_and_two_argument_calls_without_secrets():
    lifecycle = ApplicationBootstrap().create_application()
    one_arg = build_dashboard_view(lifecycle.snapshot())
    two_arg = build_dashboard_view(lifecycle.snapshot(), snapshot(), clock=ist_clock())
    assert one_arg.live_market_data.available is False
    assert two_arg.live_market_data.available is True
    assert "api_key" not in repr(two_arg.live_market_data)
    assert "access_token" not in repr(two_arg.live_market_data)


def test_market_session_before_open_and_waiting_states_are_deterministic():
    before_open = build_live_market_data_view(
        snapshot(ws=websocket(delivered_tick_count=0, last_tick_at=None)),
        clock=ist_clock(hour=6, minute=53),
    ).market_session
    assert before_open.market_status == "Waiting for NSE to open"
    assert before_open.current_time == "06:53 IST"
    assert before_open.session == "Closed"
    assert before_open.live_ticks == "Waiting"
    assert before_open.last_tick == "-"
    assert before_open.next_open == "09:15 IST"

    waiting = build_live_market_data_view(
        snapshot(ws=websocket(delivered_tick_count=0, last_tick_at=None)),
        clock=ist_clock(hour=9, minute=14),
    ).market_session
    assert waiting.market_status == "NSE pre-open"
    assert waiting.session == "Pre-Open"
    assert waiting.live_ticks == "Waiting"


def test_market_session_live_close_boundary_after_close_and_weekend():
    live = build_live_market_data_view(snapshot(), clock=ist_clock(hour=9, minute=15)).market_session
    assert live.market_status == "NSE market open"
    assert live.session == "Live"
    assert live.live_ticks == "Receiving"

    boundary = build_live_market_data_view(snapshot(), clock=ist_clock(hour=15, minute=30)).market_session
    assert boundary.market_status == "NSE market open"
    assert boundary.session == "Live"

    after_close = build_live_market_data_view(snapshot(), clock=ist_clock(hour=15, minute=31)).market_session
    assert after_close.market_status == "NSE closed for the day"
    assert after_close.session == "Closed"
    assert after_close.next_open == "Tuesday 09:15 IST"

    saturday = build_live_market_data_view(snapshot(), clock=ist_clock(day=18, hour=10, minute=0)).market_session
    assert saturday.market_status == "NSE closed - weekend"
    assert saturday.session == "Closed"
    assert saturday.next_open == "Monday 09:15 IST"

    sunday = build_live_market_data_view(snapshot(), clock=ist_clock(day=19, hour=10, minute=0)).market_session
    assert sunday.market_status == "NSE closed - weekend"
    assert sunday.next_open == "Monday 09:15 IST"


def test_market_session_websocket_disconnected_zero_ticks_and_last_tick_formatting():
    disconnected = build_live_market_data_view(
        snapshot(ws=websocket(status=ZerodhaWebSocketStatus.DISCONNECTED, connected=False, delivered_tick_count=0, last_tick_at=None)),
        clock=ist_clock(hour=10, minute=0),
    ).market_session
    assert disconnected.websocket == "Disconnected"
    assert disconnected.live_ticks == "Offline"
    assert disconnected.last_tick == "-"
    assert "1970" not in disconnected.last_tick

    waiting = build_live_market_data_view(
        snapshot(ws=websocket(delivered_tick_count=0, last_tick_at=None)),
        clock=ist_clock(hour=10, minute=0),
    ).market_session
    assert waiting.websocket == "Connected"
    assert waiting.live_ticks == "Waiting"

    receiving = build_live_market_data_view(
        snapshot(ws=websocket(delivered_tick_count=2, last_tick_at=datetime(2026, 7, 13, 4, 45, tzinfo=UTC))),
        clock=ist_clock(hour=10, minute=16),
    ).market_session
    assert receiving.live_ticks == "Receiving"
    assert receiving.last_tick == "10:15 IST"


def test_market_session_requires_timezone_aware_clock_and_formats_current_time():
    try:
        build_live_market_data_view(snapshot(), clock=lambda: datetime(2026, 7, 13, 9, 15))
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("naive clocks must be rejected")

    view = build_live_market_data_view(snapshot(), clock=ist_clock(hour=6, minute=53))
    assert view.market_session.current_time == "06:53 IST"
