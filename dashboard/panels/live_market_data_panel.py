"""
Read-only live market-data dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QGroupBox, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardLiveMarketDataView
from dashboard.widgets import FieldGrid, MetricCard, StatusBadge


class LiveMarketDataPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Live Feed", parent)
        self._labels = {}
        self._cards = {
            "Runtime Status": MetricCard("Runtime"),
            "WebSocket Status": MetricCard("WebSocket"),
            "Delivered Ticks": MetricCard("Delivered"),
            "Rejected Ticks": MetricCard("Rejected"),
        }
        self._offline_label = QLabel("Live market data not configured")
        self._offline_label.setProperty("status", "warning")
        self._offline_label.setMinimumHeight(30)
        self._offline_label.setWordWrap(True)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(("Instrument", "Exchange", "Token", "Mode"))
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setContextMenuPolicy(Qt.NoContextMenu)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setDefaultSectionSize(30)
        self._table.horizontalHeader().setMinimumHeight(34)
        self._table.setMinimumHeight(150)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 18, 14, 14)
        root.setSpacing(12)
        root.addWidget(self._offline_label)
        cards = QHBoxLayout()
        cards.setSpacing(10)
        for card in self._cards.values():
            cards.addWidget(card)
        root.addLayout(cards)
        fields = (
            "Ready",
            "Running",
            "Connected",
            "Connections",
            "Disconnections",
            "Reconnects",
            "Raw Ticks",
            "Normalized Ticks",
            "Starts",
            "Stops",
            "Last Connected",
            "Last Disconnected",
            "Last Tick",
            "Last Started",
            "Last Stopped",
            "Last Error",
        )
        grid = FieldGrid(fields)
        root.addWidget(grid)
        self._labels.update(grid.labels)
        for field, card in self._cards.items():
            self._labels[field] = card.value_label
        for field in ("Ready", "Running", "Connected"):
            badge = StatusBadge()
            grid.layout().replaceWidget(grid.labels[field], badge)
            grid.labels[field].deleteLater()
            self._labels[field] = badge
        root.addWidget(self._table)

    def render(self, view: DashboardLiveMarketDataView) -> None:
        if not isinstance(view, DashboardLiveMarketDataView):
            raise TypeError("view must be DashboardLiveMarketDataView")
        self._offline_label.setVisible(not view.available)
        self._cards["Runtime Status"].set_value(view.runtime_status)
        self._cards["WebSocket Status"].set_value(view.websocket_status)
        self._cards["Delivered Ticks"].set_value(formatters.integer(view.delivered_tick_count), kind="positive")
        self._cards["Rejected Ticks"].set_value(formatters.integer(view.rejected_tick_count), kind="negative" if view.rejected_tick_count else "neutral")
        self._labels["Ready"].set_status_text(formatters.yes_no(view.ready))
        self._labels["Running"].set_status_text(formatters.yes_no(view.running))
        self._labels["Connected"].set_status_text(formatters.yes_no(view.connected))
        self._labels["Connections"].setText(formatters.integer(view.connection_count))
        self._labels["Disconnections"].setText(formatters.integer(view.disconnection_count))
        self._labels["Reconnects"].setText(formatters.integer(view.reconnect_count))
        self._labels["Raw Ticks"].setText(formatters.integer(view.raw_tick_count))
        self._labels["Normalized Ticks"].setText(formatters.integer(view.normalized_tick_count))
        self._labels["Starts"].setText(formatters.integer(view.start_count))
        self._labels["Stops"].setText(formatters.integer(view.stop_count))
        self._labels["Last Connected"].setText(formatters.timestamp(view.last_connected_at))
        self._labels["Last Disconnected"].setText(formatters.timestamp(view.last_disconnected_at))
        self._labels["Last Tick"].setText(formatters.timestamp(view.last_tick_at))
        self._labels["Last Started"].setText(formatters.timestamp(view.last_started_at))
        self._labels["Last Stopped"].setText(formatters.timestamp(view.last_stopped_at))
        self._labels["Last Error"].setText(formatters.text(view.last_error))
        self._render_subscriptions(view)

    def _render_subscriptions(self, view: DashboardLiveMarketDataView) -> None:
        self._table.setRowCount(len(view.subscription_rows))
        for row, subscription in enumerate(view.subscription_rows):
            values = (
                subscription.instrument,
                subscription.exchange,
                str(subscription.instrument_token),
                subscription.mode,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(formatters.text(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, column, item)
        self._table.resizeColumnsToContents()
