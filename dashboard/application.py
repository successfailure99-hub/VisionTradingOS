"""
Dashboard application owner.
"""

from PySide6.QtWidgets import QApplication

from application.enums import RuntimeStatus
from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_market_data import LiveMarketDataRuntime, LiveMarketDataRuntimeStatus
from dashboard.main_window import VisionMainWindow


class DashboardApplication:
    def __init__(
        self,
        lifecycle: ApplicationLifecycleManager,
        *,
        live_market_data_runtime: LiveMarketDataRuntime | None = None,
        live_option_chain_runtime=None,
        argv: list[str] | None = None,
        refresh_interval_ms: int = 500,
        clock=None,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be an ApplicationLifecycleManager.")
        if live_market_data_runtime is not None and not isinstance(live_market_data_runtime, LiveMarketDataRuntime):
            raise TypeError("live_market_data_runtime must be a LiveMarketDataRuntime.")
        self._lifecycle = lifecycle
        self._live_market_data_runtime = live_market_data_runtime
        self._live_option_chain_runtime = live_option_chain_runtime
        self._qt_app = QApplication.instance() or QApplication(argv or [])
        self._main_window = VisionMainWindow(
            lifecycle,
            live_market_data_runtime=live_market_data_runtime,
            refresh_interval_ms=refresh_interval_ms,
            clock=clock,
        )
        self._shutdown = False

    @property
    def lifecycle(self) -> ApplicationLifecycleManager:
        return self._lifecycle

    @property
    def main_window(self) -> VisionMainWindow:
        return self._main_window

    @property
    def live_market_data_runtime(self) -> LiveMarketDataRuntime | None:
        return self._live_market_data_runtime

    @property
    def live_option_chain_runtime(self):
        return self._live_option_chain_runtime

    def run(self) -> int:
        if self._lifecycle.status is not RuntimeStatus.RUNNING:
            self._lifecycle.start()
        self._main_window.show()
        self._main_window.start_refresh()
        try:
            return int(self._qt_app.exec())
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        first_error = None
        self._main_window.stop_refresh()
        try:
            self._stop_live_option_chain_if_needed()
        except Exception as exc:
            first_error = exc
        try:
            self._stop_live_runtime_if_needed()
        except Exception as exc:
            if first_error is None:
                first_error = exc
        try:
            if self._lifecycle.status is RuntimeStatus.RUNNING:
                self._lifecycle.stop()
        except Exception as exc:
            if first_error is None:
                first_error = exc
        if first_error is not None:
            raise first_error

    def _stop_live_runtime_if_needed(self) -> None:
        runtime = self._live_market_data_runtime
        if runtime is None:
            return
        if runtime.status in {
            LiveMarketDataRuntimeStatus.STARTING,
            LiveMarketDataRuntimeStatus.RUNNING,
            LiveMarketDataRuntimeStatus.STOPPING,
            LiveMarketDataRuntimeStatus.ERROR,
        }:
            runtime.stop()

    def _stop_live_option_chain_if_needed(self) -> None:
        runtime = self._live_option_chain_runtime
        if runtime is None:
            return
        runtime.stop()
