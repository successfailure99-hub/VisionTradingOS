"""
Read-only live market-data dashboard panel.
"""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QGridLayout, QGroupBox, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from dashboard.models import DashboardLiveMarketDataView


MISSING = "-"


class LiveMarketDataPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Live Feed", parent)
        self._labels = {}
        self._offline_label = QLabel("Live market data not configured")
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(("Instrument", "Exchange", "Token", "Mode"))
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setContextMenuPolicy(Qt.NoContextMenu)

        root = QVBoxLayout(self)
        root.addWidget(self._offline_label)
        grid = QGridLayout()
        root.addLayout(grid)
        fields = (
            "Runtime Status",
            "Ready",
            "Running",
            "WebSocket Status",
            "Connected",
            "Connections",
            "Disconnections",
            "Reconnects",
            "Raw Ticks",
            "Normalized Ticks",
            "Delivered Ticks",
            "Rejected Ticks",
            "Starts",
            "Stops",
            "Last Connected",
            "Last Disconnected",
            "Last Tick",
            "Last Started",
            "Last Stopped",
            "Last Error",
        )
        for row, field in enumerate(fields):
            grid.addWidget(QLabel(field), row, 0)
            label = QLabel(MISSING)
            grid.addWidget(label, row, 1)
            self._labels[field] = label
        root.addWidget(self._table)

    def render(self, view: DashboardLiveMarketDataView) -> None:
        if not isinstance(view, DashboardLiveMarketDataView):
            raise TypeError("view must be DashboardLiveMarketDataView")
        self._offline_label.setVisible(not view.available)
        self._labels["Runtime Status"].setText(_text(view.runtime_status))
        self._labels["Ready"].setText(_bool(view.ready))
        self._labels["Running"].setText(_bool(view.running))
        self._labels["WebSocket Status"].setText(_text(view.websocket_status))
        self._labels["Connected"].setText(_bool(view.connected))
        self._labels["Connections"].setText(str(view.connection_count))
        self._labels["Disconnections"].setText(str(view.disconnection_count))
        self._labels["Reconnects"].setText(str(view.reconnect_count))
        self._labels["Raw Ticks"].setText(str(view.raw_tick_count))
        self._labels["Normalized Ticks"].setText(str(view.normalized_tick_count))
        self._labels["Delivered Ticks"].setText(str(view.delivered_tick_count))
        self._labels["Rejected Ticks"].setText(str(view.rejected_tick_count))
        self._labels["Starts"].setText(str(view.start_count))
        self._labels["Stops"].setText(str(view.stop_count))
        self._labels["Last Connected"].setText(_timestamp(view.last_connected_at))
        self._labels["Last Disconnected"].setText(_timestamp(view.last_disconnected_at))
        self._labels["Last Tick"].setText(_timestamp(view.last_tick_at))
        self._labels["Last Started"].setText(_timestamp(view.last_started_at))
        self._labels["Last Stopped"].setText(_timestamp(view.last_stopped_at))
        self._labels["Last Error"].setText(_text(view.last_error))
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
                item = QTableWidgetItem(_text(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, column, item)
        self._table.resizeColumnsToContents()


def _bool(value: bool) -> str:
    return "Yes" if value else "No"


def _text(value) -> str:
    return str(value) if value not in (None, "") else MISSING


def _timestamp(value: datetime | None) -> str:
    return value.isoformat(sep=" ", timespec="seconds") if value is not None else MISSING
