"""
Vision Trading OS desktop main window.
"""

from datetime import UTC, datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_market_data import LiveMarketDataRuntime
from dashboard.models import DashboardView
from dashboard.panels.ai_panel import AIPanel
from dashboard.panels.journal_panel import JournalPanel
from dashboard.panels.live_market_data_panel import LiveMarketDataPanel
from dashboard.panels.market_panel import MarketPanel
from dashboard.panels.option_chain_panel import OptionChainPanel
from dashboard.panels.position_panel import PositionPanel
from dashboard.panels.price_action_panel import PriceActionPanel
from dashboard.panels.runtime_panel import RuntimePanel
from dashboard.panels.strategy_panel import StrategyPanel
from dashboard.presenters import build_dashboard_view
from dashboard.theme import dashboard_stylesheet
from dashboard.widgets import StatusBadge


def _default_clock() -> datetime:
    return datetime.now(UTC)


class VisionMainWindow(QMainWindow):
    def __init__(
        self,
        lifecycle: ApplicationLifecycleManager,
        *,
        live_market_data_runtime: LiveMarketDataRuntime | None = None,
        live_option_chain_runtime=None,
        refresh_interval_ms: int = 500,
        clock=None,
        parent=None,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be an ApplicationLifecycleManager.")
        if live_market_data_runtime is not None and not isinstance(live_market_data_runtime, LiveMarketDataRuntime):
            raise TypeError("live_market_data_runtime must be a LiveMarketDataRuntime.")
        if not isinstance(refresh_interval_ms, int) or refresh_interval_ms <= 0:
            raise ValueError("refresh_interval_ms must be a positive integer.")
        super().__init__(parent)
        self._lifecycle = lifecycle
        self._live_market_data_runtime = live_market_data_runtime
        self._live_option_chain_runtime = live_option_chain_runtime
        self._current_view: DashboardView | None = None
        self._clock = clock or _default_clock
        self._runtime_panel = RuntimePanel()
        self._live_market_data_panel = LiveMarketDataPanel()
        self._main_tabs = QTabWidget()
        self._tabs = QTabWidget()
        self._system_tabs = QTabWidget()
        self._instrument_panels = {}
        self._timer = QTimer(self)
        self._timer.setInterval(refresh_interval_ms)
        self._timer.timeout.connect(self.refresh)

        self.setWindowTitle("Vision Trading OS")
        self.setMinimumSize(1100, 680)
        self.setStyleSheet(dashboard_stylesheet())
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
        live_snapshot = (
            self._live_market_data_runtime.snapshot()
            if self._live_market_data_runtime is not None
            else None
        )
        option_chain_snapshot = (
            self._live_option_chain_runtime.snapshot()
            if self._live_option_chain_runtime is not None
            else None
        )
        view = build_dashboard_view(
            lifecycle_snapshot,
            live_snapshot,
            live_option_chain_snapshot=option_chain_snapshot,
            clock=self._clock,
        )
        self.render(view)
        self._current_view = view
        return view

    def render(self, view: DashboardView) -> None:
        self._runtime_panel.render(view.runtime)
        self._live_market_data_panel.render(view.live_market_data)
        self._header_status.set_status_text(view.runtime.application_status)
        self._header_mode.set_status_text(view.runtime.safety_mode)
        self._sync_tabs(view)
        price_actions = {item.symbol: item for item in view.price_actions}
        option_chains = {item.symbol: item for item in view.option_chains}
        ai_views = {item.symbol: item for item in view.ai}
        strategies = {item.symbol: item for item in view.strategies}
        positions = {item.symbol: item for item in view.positions}
        journals = {item.symbol: item for item in view.journals}
        analytics = {item.symbol: item for item in view.analytics}
        for market in view.markets:
            panels = self._instrument_panels[market.symbol]
            panels["market"].render(market)
            panels["price_action"].render(price_actions[market.symbol])
            panels["option_chain"].render(option_chains[market.symbol])
            panels["ai"].render(ai_views[market.symbol])
            panels["strategy"].render(strategies[market.symbol])
            panels["position"].render(positions[market.symbol])
            panels["journal"].render(journals[market.symbol])
            panels["journal"].render_analytics(analytics[market.symbol])
        self.statusBar().showMessage(f"Application {view.runtime.application_status}")

    def current_view(self) -> DashboardView | None:
        return self._current_view

    def closeEvent(self, event):
        self.stop_refresh()
        super().closeEvent(event)

    def _build_layout(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(12)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_main_tabs(), 1)
        self.setCentralWidget(root)

    def _build_main_tabs(self) -> QTabWidget:
        trading = QWidget()
        trading_layout = QVBoxLayout(trading)
        trading_layout.setContentsMargins(0, 0, 0, 0)
        trading_layout.addWidget(self._tabs, 1)

        system = QWidget()
        system_layout = QVBoxLayout(system)
        system_layout.setContentsMargins(0, 0, 0, 0)
        self._system_tabs.addTab(self._scroll_area(self._runtime_panel), "Runtime")
        self._system_tabs.addTab(self._scroll_area(self._live_market_data_panel), "Live Feed")
        system_layout.addWidget(self._system_tabs, 1)

        self._main_tabs.addTab(trading, "Trading")
        self._main_tabs.addTab(system, "System")
        return self._main_tabs

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("ApplicationHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 14, 18, 14)
        title_area = QVBoxLayout()
        title = QLabel("Vision Trading OS")
        title.setObjectName("HeaderTitle")
        subtitle = QLabel("Dashboard V1 - ANALYSIS_ONLY / DRY_RUN")
        subtitle.setObjectName("HeaderSubtitle")
        title_area.addWidget(title)
        title_area.addWidget(subtitle)
        layout.addLayout(title_area, 1)
        self._header_mode = StatusBadge()
        self._header_status = StatusBadge()
        layout.addWidget(self._header_mode, 0, Qt.AlignRight)
        layout.addWidget(self._header_status, 0, Qt.AlignRight)
        return header

    def _sync_tabs(self, view: DashboardView) -> None:
        selected_symbol = self._tabs.tabText(self._tabs.currentIndex()) if self._tabs.currentIndex() >= 0 else None
        selected_inner_tabs = {
            symbol: panels["sections"].tabText(panels["sections"].currentIndex())
            for symbol, panels in self._instrument_panels.items()
            if panels["sections"].currentIndex() >= 0
        }
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
        for target_index, symbol in enumerate(required):
            widget = self._instrument_panels[symbol]["tab"]
            current_index = self._tabs.indexOf(widget)
            if current_index != target_index:
                self._tabs.removeTab(current_index)
                self._tabs.insertTab(target_index, widget, symbol)
        if selected_symbol in self._instrument_panels:
            self._tabs.setCurrentWidget(self._instrument_panels[selected_symbol]["tab"])
        for symbol, tab_name in selected_inner_tabs.items():
            if symbol in self._instrument_panels:
                sections = self._instrument_panels[symbol]["sections"]
                for index in range(sections.count()):
                    if sections.tabText(index) == tab_name:
                        sections.setCurrentIndex(index)
                        break

    def _add_instrument_tab(self, symbol: str) -> None:
        tab = QWidget()
        root = QVBoxLayout(tab)
        root.setContentsMargins(0, 0, 0, 0)
        sections = QTabWidget()

        market = MarketPanel()
        price_action = PriceActionPanel()
        option_chain = OptionChainPanel()
        ai = AIPanel()
        strategy = StrategyPanel()
        position = PositionPanel()
        journal = JournalPanel()

        sections.addTab(self._scroll_area(market), "Market")
        sections.addTab(self._scroll_area(price_action), "Price Action")
        sections.addTab(option_chain, "Option Chain")
        sections.addTab(self._scroll_area(ai), "AI")
        sections.addTab(self._scroll_area(strategy), "Strategy")
        sections.addTab(self._scroll_area(position), "Position")
        sections.addTab(self._scroll_area(journal), "Journal")
        root.addWidget(sections)
        self._tabs.addTab(tab, symbol)
        self._instrument_panels[symbol] = {
            "tab": tab,
            "sections": sections,
            "market": market,
            "price_action": price_action,
            "option_chain": option_chain,
            "ai": ai,
            "strategy": strategy,
            "position": position,
            "journal": journal,
        }

    def _scroll_area(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        scroll.setWidget(widget)
        return scroll
