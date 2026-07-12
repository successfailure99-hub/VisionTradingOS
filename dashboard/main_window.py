"""
Vision Trading OS desktop main window.
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QSplitter, QTabWidget, QVBoxLayout, QWidget

from application.lifecycle_manager import ApplicationLifecycleManager
from dashboard.models import DashboardView
from dashboard.panels.ai_panel import AIPanel
from dashboard.panels.journal_panel import JournalPanel
from dashboard.panels.market_panel import MarketPanel
from dashboard.panels.position_panel import PositionPanel
from dashboard.panels.runtime_panel import RuntimePanel
from dashboard.panels.strategy_panel import StrategyPanel
from dashboard.presenters import build_dashboard_view


class VisionMainWindow(QMainWindow):
    def __init__(
        self,
        lifecycle: ApplicationLifecycleManager,
        *,
        refresh_interval_ms: int = 500,
        parent=None,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be an ApplicationLifecycleManager.")
        if not isinstance(refresh_interval_ms, int) or refresh_interval_ms <= 0:
            raise ValueError("refresh_interval_ms must be a positive integer.")
        super().__init__(parent)
        self._lifecycle = lifecycle
        self._current_view: DashboardView | None = None
        self._runtime_panel = RuntimePanel()
        self._tabs = QTabWidget()
        self._instrument_panels = {}
        self._timer = QTimer(self)
        self._timer.setInterval(refresh_interval_ms)
        self._timer.timeout.connect(self.refresh)

        self.setWindowTitle("Vision Trading OS")
        self.setMinimumSize(1100, 720)
        self._build_layout()
        self.statusBar().showMessage("Application created")

    def start_refresh(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop_refresh(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def refresh(self) -> DashboardView:
        lifecycle_snapshot = self._lifecycle.snapshot()
        view = build_dashboard_view(lifecycle_snapshot)
        self.render(view)
        self._current_view = view
        return view

    def render(self, view: DashboardView) -> None:
        self._runtime_panel.render(view.runtime)
        self._sync_tabs(view)
        for index, market in enumerate(view.markets):
            panels = self._instrument_panels[market.symbol]
            panels["market"].render(market)
            panels["ai"].render(view.ai[index])
            panels["strategy"].render(view.strategies[index])
            panels["position"].render(view.positions[index])
            panels["journal"].render(view.journals[index])
        self.statusBar().showMessage(f"Application {view.runtime.application_status}")

    def current_view(self) -> DashboardView | None:
        return self._current_view

    def closeEvent(self, event):
        self.stop_refresh()
        super().closeEvent(event)

    def _build_layout(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self._runtime_panel)
        layout.addWidget(self._tabs, 1)
        self.setCentralWidget(root)

    def _sync_tabs(self, view: DashboardView) -> None:
        existing = set(self._instrument_panels)
        required = tuple(market.symbol for market in view.markets)
        for symbol in required:
            if symbol not in self._instrument_panels:
                self._add_instrument_tab(symbol)
        for symbol in existing - set(required):
            widget = self._instrument_panels.pop(symbol)["tab"]
            index = self._tabs.indexOf(widget)
            if index >= 0:
                self._tabs.removeTab(index)

    def _add_instrument_tab(self, symbol: str) -> None:
        tab = QWidget()
        root = QHBoxLayout(tab)
        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)

        market = MarketPanel()
        ai = AIPanel()
        strategy = StrategyPanel()
        position = PositionPanel()
        journal = JournalPanel()

        left_layout.addWidget(market)
        left_layout.addWidget(ai)
        right_layout.addWidget(strategy)
        right_layout.addWidget(position)
        right_layout.addWidget(journal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        root.addWidget(splitter)
        self._tabs.addTab(tab, symbol)
        self._instrument_panels[symbol] = {
            "tab": tab,
            "market": market,
            "ai": ai,
            "strategy": strategy,
            "position": position,
            "journal": journal,
        }
