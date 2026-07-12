"""
Tests for live market-data dashboard presentation models.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime

import pytest

from dashboard.models import (
    DashboardLiveMarketDataView,
    DashboardLiveSubscriptionView,
    DashboardRuntimeView,
    DashboardView,
    unavailable_live_market_data_view,
)


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def live_view(**overrides):
    values = dict(
        available=True,
        runtime_status="Running",
        ready=True,
        running=True,
        websocket_status="Connected",
        connected=True,
        configured_instruments=("NIFTY",),
        configured_tokens=(101,),
        subscription_count=1,
        subscription_rows=(DashboardLiveSubscriptionView("NIFTY", "NSE", 101, "Full"),),
        connection_count=1,
        disconnection_count=0,
        reconnect_count=0,
        raw_tick_count=1,
        normalized_tick_count=1,
        delivered_tick_count=1,
        rejected_tick_count=0,
        start_count=1,
        stop_count=0,
        last_connected_at=NOW,
        last_disconnected_at=None,
        last_tick_at=NOW,
        last_started_at=NOW,
        last_stopped_at=None,
        last_error=None,
    )
    values.update(overrides)
    return DashboardLiveMarketDataView(**values)


def test_live_subscription_view_is_immutable():
    row = DashboardLiveSubscriptionView("NIFTY", "NSE", 101, "Full")
    with pytest.raises(FrozenInstanceError):
        row.instrument = "BANKNIFTY"


def test_live_runtime_view_is_immutable_and_tuple_fields_are_immutable():
    view = live_view()
    with pytest.raises(FrozenInstanceError):
        view.running = False
    assert isinstance(view.configured_instruments, tuple)
    assert isinstance(view.configured_tokens, tuple)
    assert isinstance(view.subscription_rows, tuple)


def test_negative_counts_and_naive_timestamps_are_rejected():
    with pytest.raises(ValueError):
        live_view(raw_tick_count=-1)
    with pytest.raises(ValueError):
        live_view(last_tick_at=datetime(2026, 7, 12, 9, 15))


def test_secret_and_backend_owner_fields_are_absent():
    names = {field.name for field in fields(DashboardLiveMarketDataView)}
    assert names.isdisjoint(
        {
            "api_key",
            "api_secret",
            "access_token",
            "request_token",
            "session",
            "websocket_client",
            "lifecycle",
            "runtime",
            "raw_tick",
        }
    )


def test_unavailable_view_accepts_empty_state_and_subscription_order_is_preserved():
    unavailable = unavailable_live_market_data_view()
    assert unavailable.available is False
    assert unavailable.subscription_rows == ()
    first = DashboardLiveSubscriptionView("NIFTY", "NSE", 101, "Full")
    second = DashboardLiveSubscriptionView("SENSEX", "BSE", 202, "Quote")
    view = live_view(subscription_count=2, subscription_rows=(first, second))
    assert view.subscription_rows == (first, second)


def test_existing_dashboard_view_remains_immutable_with_default_live_view():
    runtime = DashboardRuntimeView("Created", "Dry Run", "Analysis Only", ("NIFTY",), False, False, 0, 0, 0, None, None, None)
    dashboard = DashboardView(runtime, (), (), (), (), ())
    assert dashboard.live_market_data.available is False
    with pytest.raises(FrozenInstanceError):
        dashboard.markets = ()
