"""
Dashboard application owner.
"""

from PySide6.QtWidgets import QApplication

from application.enums import RuntimeStatus
from application.lifecycle_manager import ApplicationLifecycleManager
from dashboard.main_window import VisionMainWindow


class DashboardApplication:
    def __init__(
        self,
        lifecycle: ApplicationLifecycleManager,
        *,
        argv: list[str] | None = None,
        refresh_interval_ms: int = 500,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be an ApplicationLifecycleManager.")
        self._lifecycle = lifecycle
        self._qt_app = QApplication.instance() or QApplication(argv or [])
        self._main_window = VisionMainWindow(lifecycle, refresh_interval_ms=refresh_interval_ms)
        self._shutdown = False

    @property
    def lifecycle(self) -> ApplicationLifecycleManager:
        return self._lifecycle

    @property
    def main_window(self) -> VisionMainWindow:
        return self._main_window

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
        self._main_window.stop_refresh()
        if self._lifecycle.status is RuntimeStatus.RUNNING:
            self._lifecycle.stop()
