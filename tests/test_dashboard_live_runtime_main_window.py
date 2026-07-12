"""
Tests for live runtime observation in the dashboard main window.
"""

import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from application import ApplicationBootstrap
from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_market_data import LiveMarketDataRuntime, LiveMarketDataRuntimeSnapshot, LiveMarketDataRuntimeStatus
from dashboard.main_window import VisionMainWindow


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def app():
    return QApplication.instance() or QApplication([])


class CountingLifecycle(ApplicationLifecycleManager):
    def __init__(self):
        super().__init__(ApplicationBootstrap().create_application().orchestrator)
        self.snapshot_calls = 0
        self.stop_calls = 0

    def snapshot(self):
        self.snapshot_calls += 1
        return super().snapshot()

    def stop(self):
        self.stop_calls += 1
        return super().stop()


class FakeLiveRuntime(LiveMarketDataRuntime):
    def __init__(self):
        self.snapshot_calls = 0
        self.start_calls = 0
        self.stop_calls = 0

    def snapshot(self):
        self.snapshot_calls += 1
        return LiveMarketDataRuntimeSnapshot(
            status=LiveMarketDataRuntimeStatus.CREATED,
            ready=False,
            running=False,
            configured_instruments=(),
            configured_tokens=(),
            websocket=None,
            start_count=0,
            stop_count=0,
            last_started_at=None,
            last_stopped_at=None,
            last_error=None,
        )

    def start(self):
        self.start_calls += 1
        return self.snapshot()

    def stop(self):
        self.stop_calls += 1
        return self.snapshot()


def test_existing_constructor_without_runtime_still_works_and_invalid_runtime_rejected():
    app()
    window = VisionMainWindow(ApplicationBootstrap().create_application())
    assert window.current_view() is None
    with pytest.raises(TypeError):
        VisionMainWindow(ApplicationBootstrap().create_application(), live_market_data_runtime=object())


def test_constructor_does_not_start_or_stop_supplied_runtime_and_preserves_tabs():
    app()
    runtime = FakeLiveRuntime()
    window = VisionMainWindow(ApplicationBootstrap().create_application(), live_market_data_runtime=runtime)
    view = window.refresh()
    assert runtime.start_calls == 0
    assert runtime.stop_calls == 0
    assert window._tabs.count() == len(view.markets)
    assert window._live_market_data_panel is not None


def test_refresh_without_runtime_calls_lifecycle_once_and_no_live_snapshot():
    app()
    lifecycle = CountingLifecycle()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()
    assert lifecycle.snapshot_calls == 1
    assert view.live_market_data.available is False


def test_refresh_with_runtime_calls_each_snapshot_once_and_stores_combined_view():
    app()
    lifecycle = CountingLifecycle()
    runtime = FakeLiveRuntime()
    window = VisionMainWindow(lifecycle, live_market_data_runtime=runtime)
    view = window.refresh()
    assert lifecycle.snapshot_calls == 1
    assert runtime.snapshot_calls == 1
    assert window.current_view() is view
    assert view.live_market_data.available is True


def test_refresh_timer_idempotent_and_close_stops_timer_only():
    app()
    lifecycle = CountingLifecycle()
    runtime = FakeLiveRuntime()
    window = VisionMainWindow(lifecycle, live_market_data_runtime=runtime)
    assert window._timer.interval() == 500
    window.start_refresh()
    window.start_refresh()
    assert window._timer.isActive()
    window.stop_refresh()
    window.stop_refresh()
    assert not window._timer.isActive()
    window.start_refresh()
    window.close()
    assert not window._timer.isActive()
    assert runtime.stop_calls == 0
    assert lifecycle.stop_calls == 0
