"""
Vision Trading OS desktop main window.
"""

from datetime import UTC, datetime
from time import perf_counter

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_market_data import LiveMarketDataRuntime
from application.runtime_supervisor import RuntimeSupervisor
from dashboard import formatters
from dashboard.models import DashboardView
from dashboard.panels.ai_panel import AIPanel
from dashboard.panels.backtest_panel import BacktestPanel
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
from desktop.vision_method import VisionMethodInspector, VisionMethodLiveInspectorBridge


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _bind_signal(signal, callback) -> None:
    getattr(signal, "connect")(callback)


class VisionMainWindow(QMainWindow):
    def __init__(
        self,
        lifecycle: ApplicationLifecycleManager,
        *,
        live_market_data_runtime: LiveMarketDataRuntime | None = None,
        live_option_chain_runtime=None,
        historical_replay_driver=None,
        deterministic_backtest_driver=None,
        refresh_interval_ms: int = 500,
        clock=None,
        settings=None,
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
        self._historical_replay_driver = historical_replay_driver
        self._deterministic_backtest_driver = deterministic_backtest_driver
        self._current_view: DashboardView | None = None
        self._last_rendered_view: DashboardView | None = None
        self._rendering = False
        self._panel_render_cache = {}
        self._slow_threshold_ms = 100.0
        self._diagnostics = {
            "snapshot_retrieval_ms": 0.0,
            "presenter_construction_ms": 0.0,
            "active_panel_render_ms": 0.0,
            "visible_panel_switch_ms": 0.0,
            "tab_change_ms": 0.0,
            "dashboard_render_ms": 0.0,
            "runtime_supervisor_ms": 0.0,
            "vision_method_bridge_ms": 0.0,
            "ui_responsiveness": "HEALTHY",
            "tab_change_p50_ms": 0.0,
            "tab_change_p95_ms": 0.0,
            "tab_change_p99_ms": 0.0,
            "slow_operations": (),
        }
        self._tab_change_samples = ()
        self._clock = clock or _default_clock
        self._settings = settings or QSettings("VisionTradingOS", "Dashboard")
        self._favorite_sections = tuple(str(item) for item in (self._settings.value("favorites", []) or ()))
        self._pending_state_restore = True
        self._runtime_panel = RuntimePanel()
        self._live_market_data_panel = LiveMarketDataPanel()
        self._backtest_panel = BacktestPanel(command_target=lifecycle.orchestrator)
        self._vision_method_inspector = VisionMethodInspector()
        self._vision_method_bridge = VisionMethodLiveInspectorBridge(lifecycle, self._vision_method_inspector)
        self._runtime_supervisor = RuntimeSupervisor(lifecycle, interval_ms=refresh_interval_ms)
        self._last_lifecycle_snapshot = None
        self._main_tabs = QTabWidget()
        self._tabs = QTabWidget()
        self._system_tabs = QTabWidget()
        self._tab_bar_owners = {}
        self._health_badges = {}
        self._instrument_panels = {}
        self._timer = QTimer(self)
        self._timer.setInterval(refresh_interval_ms)
        _bind_signal(self._timer.timeout, self.refresh)
        _bind_signal(self._main_tabs.currentChanged, self._profile_tab_change)
        _bind_signal(self._tabs.currentChanged, self._profile_tab_change)
        _bind_signal(self._system_tabs.currentChanged, self._profile_tab_change)

        self.setWindowTitle("Vision Trading OS")
        self.setMinimumSize(1100, 680)
        self.setStyleSheet(dashboard_stylesheet())
        self._build_layout()
        self._install_navigation_shortcuts()
        self._restore_window_state()
        self.statusBar().showMessage("Application created")

    def start_refresh(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop_refresh(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def refresh(self) -> DashboardView:
        if self._rendering:
            return self._current_view if self._current_view is not None else self._build_view()
        if self._historical_replay_driver is not None:
            self._historical_replay_driver.poll()
        if self._deterministic_backtest_driver is not None:
            self._deterministic_backtest_driver.poll()
        bridge_started = perf_counter()
        self._vision_method_bridge.refresh()
        self._record_duration("vision_method_bridge_ms", bridge_started)
        view = self._build_view()
        supervisor_started = perf_counter()
        self._runtime_supervisor.monitor(self._last_lifecycle_snapshot)
        self._record_duration("runtime_supervisor_ms", supervisor_started)
        self._current_view = view
        if view != self._last_rendered_view:
            self.render(view)
        return view

    def _build_view(self) -> DashboardView:
        started = perf_counter()
        lifecycle_snapshot = self._lifecycle.snapshot()
        self._last_lifecycle_snapshot = lifecycle_snapshot
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
        self._record_duration("snapshot_retrieval_ms", started)
        started = perf_counter()
        view = build_dashboard_view(
            lifecycle_snapshot,
            live_snapshot,
            live_option_chain_snapshot=option_chain_snapshot,
            clock=self._clock,
        )
        self._record_duration("presenter_construction_ms", started)
        return view

    def render(self, view: DashboardView) -> None:
        if self._rendering:
            return
        self._current_view = view
        self._rendering = True
        started = perf_counter()
        try:
            self._header_status.set_status_text(view.runtime.application_status)
            self._header_mode.set_status_text(view.runtime.safety_mode)
            self._update_header_health(view)
            self._sync_tabs(view)
            panel_started = perf_counter()
            self._render_visible_panels(view)
            self._record_duration("active_panel_render_ms", panel_started)
            self.statusBar().showMessage(f"Application {view.runtime.application_status}")
            self._last_rendered_view = view
        finally:
            self._record_duration("dashboard_render_ms", started)
            self._rendering = False

    def current_view(self) -> DashboardView | None:
        return self._current_view

    def diagnostics(self) -> dict[str, object]:
        return dict(self._diagnostics)

    def render_vision_method(self, snapshot, report) -> None:
        self._vision_method_inspector.render(snapshot, report)

    def _render_current_view(self, *_args) -> None:
        if self._current_view is not None:
            started = perf_counter()
            self._render_visible_panels(self._current_view)
            self._record_duration("active_panel_render_ms", started)

    def _profile_tab_change(self, *_args) -> None:
        if self._current_view is None:
            return
        started = perf_counter()
        self._render_visible_panels(self._current_view)
        self._record_duration("visible_panel_switch_ms", started)
        self._record_tab_change(started)

    def _render_visible_panels(self, view: DashboardView) -> None:
        if self._main_tabs.currentWidget() is self._system_area:
            current_system = self._system_tabs.currentWidget()
            if current_system is self._system_tabs.widget(0):
                self._render_cached(("system", "Runtime"), view.runtime, self._runtime_panel.render)
            elif current_system is self._system_tabs.widget(1):
                self._render_cached(("system", "Live Feed"), view.live_market_data, self._live_market_data_panel.render)
            elif current_system is self._system_tabs.widget(2):
                self._render_cached(("system", "Backtest"), view.backtest, self._backtest_panel.render)
            return
        if self._main_tabs.currentWidget() is self._vision_method_area:
            return
        if self._tabs.currentIndex() < 0:
            return
        symbol = self._tabs.tabText(self._tabs.currentIndex())
        self._render_instrument_panels(view, symbol)

    def _render_instrument_panels(self, view: DashboardView, symbol: str) -> None:
        if symbol not in self._instrument_panels:
            return
        markets = {item.symbol: item for item in view.markets}
        if symbol not in markets:
            return
        price_actions = {item.symbol: item for item in view.price_actions}
        option_chains = {item.symbol: item for item in view.option_chains}
        ai_views = {item.symbol: item for item in view.ai}
        strategies = {item.symbol: item for item in view.strategies}
        positions = {item.symbol: item for item in view.positions}
        journals = {item.symbol: item for item in view.journals}
        analytics = {item.symbol: item for item in view.analytics}
        panels = self._instrument_panels[symbol]
        active_section = panels["sections"].tabText(panels["sections"].currentIndex())
        if active_section == "Market":
            self._render_cached((symbol, "Market"), markets[symbol], panels["market"].render)
        if active_section == "Price Action":
            self._render_cached((symbol, "Price Action"), price_actions[symbol], panels["price_action"].render)
        if active_section == "Option Chain":
            self._render_cached((symbol, "Option Chain"), option_chains[symbol], panels["option_chain"].render)
        if active_section == "AI":
            self._render_cached((symbol, "AI"), ai_views[symbol], panels["ai"].render)
        if active_section == "Strategy":
            self._render_cached((symbol, "Strategy"), strategies[symbol], panels["strategy"].render)
        if active_section == "Position":
            self._render_cached((symbol, "Position"), positions[symbol], panels["position"].render)
        if active_section == "Journal":
            self._render_cached((symbol, "Journal"), journals[symbol], panels["journal"].render)
            self._render_cached((symbol, "Analytics"), analytics[symbol], panels["journal"].render_analytics)

    def closeEvent(self, event):
        self._save_window_state()
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
        self._trading_area = trading
        trading_layout = QVBoxLayout(trading)
        trading_layout.setContentsMargins(0, 0, 0, 0)
        trading_layout.addWidget(self._tabs, 1)

        vision_method = QWidget()
        self._vision_method_area = vision_method
        vision_layout = QVBoxLayout(vision_method)
        vision_layout.setContentsMargins(0, 0, 0, 0)
        vision_layout.addWidget(self._scroll_area(self._vision_method_inspector), 1)

        system = QWidget()
        self._system_area = system
        system_layout = QVBoxLayout(system)
        system_layout.setContentsMargins(0, 0, 0, 0)
        self._system_tabs.addTab(self._scroll_area(self._runtime_panel), "Runtime")
        self._system_tabs.addTab(self._scroll_area(self._live_market_data_panel), "Live Feed")
        self._system_tabs.addTab(self._scroll_area(self._backtest_panel), "Backtest")
        system_layout.addWidget(self._system_tabs, 1)

        self._main_tabs.addTab(trading, "Trading")
        self._main_tabs.addTab(vision_method, "Vision Method")
        self._main_tabs.addTab(system, "System")
        self._register_tab_bar(self._main_tabs)
        self._register_tab_bar(self._tabs)
        self._register_tab_bar(self._system_tabs)
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
        self._quick_search = QLineEdit()
        self._quick_search.setPlaceholderText("Search panels")
        self._quick_search.setMaximumWidth(220)
        self._quick_search.hide()
        _bind_signal(self._quick_search.returnPressed, self._activate_quick_search)
        layout.addWidget(self._quick_search, 0, Qt.AlignRight)
        for name in ("Runtime", "Market", "Broker", "Option Chain", "Vision", "Paper", "AI"):
            badge = StatusBadge()
            badge.set_status_text("Waiting")
            self._health_badges[name] = badge
            layout.addWidget(badge, 0, Qt.AlignRight)
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
        if self._pending_state_restore:
            self._restore_tab_state()
            self._pending_state_restore = False

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

        section_widgets = {
            "Market": self._scroll_area(market),
            "Price Action": self._scroll_area(price_action),
            "Option Chain": option_chain,
            "AI": self._scroll_area(ai),
            "Strategy": self._scroll_area(strategy),
            "Position": self._scroll_area(position),
            "Journal": self._scroll_area(journal),
        }
        for name in self._ordered_section_names(tuple(section_widgets)):
            sections.addTab(section_widgets[name], name)
        root.addWidget(sections)
        self._tabs.addTab(tab, symbol)
        self._register_tab_bar(sections)
        _bind_signal(sections.currentChanged, self._profile_tab_change)
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

    def _record_duration(self, field_name: str, started: float) -> None:
        elapsed_ms = max(0.0, (perf_counter() - started) * 1000.0)
        self._diagnostics[field_name] = elapsed_ms
        if field_name in {"tab_change_ms", "visible_panel_switch_ms", "dashboard_render_ms"}:
            self._diagnostics["ui_responsiveness"] = _responsiveness(elapsed_ms)
        if elapsed_ms >= self._slow_threshold_ms:
            rows = tuple(self._diagnostics.get("slow_operations", ()))
            self._diagnostics["slow_operations"] = rows[-15:] + ((field_name, elapsed_ms),)

    def _record_tab_change(self, started: float) -> None:
        self._record_duration("tab_change_ms", started)
        samples = (self._tab_change_samples + (float(self._diagnostics["tab_change_ms"]),))[-500:]
        self._tab_change_samples = samples
        self._diagnostics["tab_change_p50_ms"] = _percentile(samples, 50)
        self._diagnostics["tab_change_p95_ms"] = _percentile(samples, 95)
        self._diagnostics["tab_change_p99_ms"] = _percentile(samples, 99)

    def _render_cached(self, key: tuple[str, str], value, renderer) -> None:
        if self._panel_render_cache.get(key) == value:
            return
        renderer(value)
        self._panel_render_cache[key] = value

    def _install_navigation_shortcuts(self) -> None:
        for sequence, section in (
            ("Ctrl+1", "Market"),
            ("Ctrl+2", "Price Action"),
            ("Ctrl+3", "Option Chain"),
            ("Ctrl+4", "AI"),
            ("Ctrl+5", "Strategy"),
            ("Ctrl+6", "Position"),
            ("Ctrl+7", "Journal"),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            _bind_signal(shortcut.activated, lambda section=section: self._select_section(section))
        next_shortcut = QShortcut(QKeySequence("Ctrl+Tab"), self)
        previous_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        search_shortcut = QShortcut(QKeySequence("Ctrl+P"), self)
        _bind_signal(next_shortcut.activated, self._select_next_panel)
        _bind_signal(previous_shortcut.activated, self._select_previous_panel)
        _bind_signal(search_shortcut.activated, self._show_quick_search)

    def _register_tab_bar(self, tabs: QTabWidget) -> None:
        bar = tabs.tabBar()
        self._tab_bar_owners[bar] = tabs
        bar.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and obj in self._tab_bar_owners:
            delta = event.angleDelta().y()
            self._advance_tab(self._tab_bar_owners[obj], -1 if delta > 0 else 1)
            return True
        return super().eventFilter(obj, event)

    def _select_section(self, section: str) -> None:
        if self._tabs.currentIndex() < 0:
            return
        symbol = self._tabs.tabText(self._tabs.currentIndex())
        panels = self._instrument_panels.get(symbol)
        if panels is None:
            return
        self._main_tabs.setCurrentWidget(self._trading_area)
        sections = panels["sections"]
        for index in range(sections.count()):
            if sections.tabText(index) == section:
                sections.setCurrentIndex(index)
                return

    def _select_next_panel(self) -> None:
        self._advance_tab(self._active_tab_widget(), 1)

    def _select_previous_panel(self) -> None:
        self._advance_tab(self._active_tab_widget(), -1)

    def _active_tab_widget(self) -> QTabWidget:
        if self._main_tabs.currentWidget() is self._system_area:
            return self._system_tabs
        if self._main_tabs.currentWidget() is self._trading_area and self._tabs.currentIndex() >= 0:
            symbol = self._tabs.tabText(self._tabs.currentIndex())
            panels = self._instrument_panels.get(symbol)
            if panels is not None:
                return panels["sections"]
        return self._main_tabs

    def _advance_tab(self, tabs: QTabWidget, step: int) -> None:
        if tabs.count() <= 0:
            return
        tabs.setCurrentIndex((tabs.currentIndex() + step) % tabs.count())

    def _show_quick_search(self) -> None:
        self._quick_search.show()
        self._quick_search.setFocus(Qt.ShortcutFocusReason)
        self._quick_search.selectAll()

    def _activate_quick_search(self) -> None:
        query = self._quick_search.text().strip().casefold()
        if not query:
            return
        aliases = {
            "adr": "Vision Method",
            "vwap": "Vision Method",
            "cpr": "Vision Method",
            "liquidity": "Vision Method",
            "vision": "Vision Method",
            "risk": "Strategy",
        }
        target = aliases.get(query, None)
        for section in ("Market", "Price Action", "Option Chain", "AI", "Strategy", "Position", "Journal"):
            if query in section.casefold():
                target = section
                break
        if query in {"runtime", "system"}:
            self._main_tabs.setCurrentWidget(self._system_area)
            self._system_tabs.setCurrentIndex(0)
        elif target == "Vision Method":
            self._main_tabs.setCurrentWidget(self._vision_method_area)
        elif target is not None:
            self._select_section(target)
        self._quick_search.hide()

    def pin_panel(self, section: str) -> None:
        if not isinstance(section, str) or not section.strip():
            raise ValueError("section must be non-empty text")
        section = section.strip()
        if section not in self._favorite_sections:
            self._favorite_sections = (section, *self._favorite_sections)
            self._settings.setValue("favorites", list(self._favorite_sections))

    def _ordered_section_names(self, names: tuple[str, ...]) -> tuple[str, ...]:
        favorites = tuple(name for name in self._favorite_sections if name in names)
        return favorites + tuple(name for name in names if name not in favorites)

    def _restore_window_state(self) -> None:
        geometry = self._settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        size = self._settings.value("window_size")
        if size is not None and hasattr(size, "isValid") and size.isValid():
            self.resize(size)
        position = self._settings.value("window_position")
        if position is not None:
            self.move(position)

    def _restore_tab_state(self) -> None:
        main_tab = self._settings.value("main_tab")
        if isinstance(main_tab, str):
            self._select_tab_by_name(self._main_tabs, main_tab)
        instrument = self._settings.value("instrument")
        if isinstance(instrument, str):
            self._select_tab_by_name(self._tabs, instrument)
        section = self._settings.value("section")
        if isinstance(section, str) and self._tabs.currentIndex() >= 0:
            symbol = self._tabs.tabText(self._tabs.currentIndex())
            panels = self._instrument_panels.get(symbol)
            if panels is not None:
                self._select_tab_by_name(panels["sections"], section)

    def _save_window_state(self) -> None:
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("window_position", self.pos())
        self._settings.setValue("window_size", self.size())
        self._settings.setValue("main_tab", self._main_tabs.tabText(self._main_tabs.currentIndex()) if self._main_tabs.currentIndex() >= 0 else "Trading")
        self._settings.setValue("instrument", self._tabs.tabText(self._tabs.currentIndex()) if self._tabs.currentIndex() >= 0 else "")
        if self._tabs.currentIndex() >= 0:
            panels = self._instrument_panels.get(self._tabs.tabText(self._tabs.currentIndex()))
            if panels is not None:
                sections = panels["sections"]
                self._settings.setValue("section", sections.tabText(sections.currentIndex()) if sections.currentIndex() >= 0 else "")
        self._settings.setValue("favorites", list(self._favorite_sections))

    def _select_tab_by_name(self, tabs: QTabWidget, name: str) -> None:
        for index in range(tabs.count()):
            if tabs.tabText(index) == name:
                tabs.setCurrentIndex(index)
                return

    def _update_header_health(self, view: DashboardView) -> None:
        health = {row.name: row for row in view.runtime.component_health}
        summary = view.runtime.runtime_health_summary
        values = {
            "Runtime": (
                f"Runtime: {summary.overall_status}",
                formatters.semantic_kind(summary.overall_status),
                summary.tooltip,
            ),
            "Market": "READY" if view.runtime.market_data_ready else "WAITING",
            "Broker": view.runtime.broker_authentication or view.runtime.broker_connection,
            "Option Chain": health.get("Option Chain").status if health.get("Option Chain") is not None else "WAITING",
            "Vision": view.runtime.vision_readiness,
            "Paper": view.runtime.paper_readiness,
            "AI": "READY" if any(item.explanation != "-" for item in view.ai) else "WAITING",
        }
        tooltips = {
            "Runtime": summary.tooltip,
            "Market": _header_tooltip(
                "Market Data",
                values["Market"],
                "Runtime market data is ready." if view.runtime.market_data_ready else "Market data is waiting.",
            ),
            "Broker": _header_tooltip(
                "Broker API Account Auth",
                values["Broker"],
                view.runtime.broker_blocking_reason,
            ),
            "Option Chain": _component_header_tooltip("Option Chain", health.get("Option Chain")),
            "Vision": _header_tooltip("Vision Method", values["Vision"], view.runtime.primary_blocker),
            "Paper": _header_tooltip("Paper Trading", values["Paper"], view.runtime.journal_persistence_status),
            "AI": _header_tooltip("AI Explanation", values["AI"], "Explanation available." if values["AI"] == "READY" else "AI explanation is waiting."),
        }
        for name, payload in values.items():
            if isinstance(payload, tuple):
                status_text, kind, tooltip = payload
                self._health_badges[name].set_status_text(status_text, kind=kind)
                self._health_badges[name].setToolTip(tooltip)
            else:
                self._health_badges[name].set_status_text(payload)
                self._health_badges[name].setToolTip(tooltips[name])


def _runtime_header_status(view: DashboardView) -> str:
    return view.runtime.runtime_health_summary.overall_status


def _component_header_tooltip(component: str, row) -> str:
    if row is None:
        return _header_tooltip(component, "WAITING", "Component health row is not available.")
    return _header_tooltip(component, row.status, row.detail)


def _header_tooltip(component: str, status, reason) -> str:
    reason_text = str(reason or "None").strip()
    if reason_text in {"", "-", "none", "None", "NONE"}:
        reason_text = "None"
    return "\n".join(
        (
            f"Component: {component}",
            f"Status: {status}",
            f"Reason: {reason_text}",
        )
    )


def _percentile(samples: tuple[float, ...], percentile: int) -> float:
    if not samples:
        return 0.0
    values = sorted(samples)
    index = round((len(values) - 1) * (percentile / 100.0))
    return values[max(0, min(index, len(values) - 1))]


def _responsiveness(elapsed_ms: float) -> str:
    if elapsed_ms < 50.0:
        return "HEALTHY"
    if elapsed_ms < 100.0:
        return "NOTICE"
    if elapsed_ms < 250.0:
        return "SLOW"
    return "UI_STALL"
