"""
Runtime status dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QGroupBox, QHBoxLayout, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardRuntimeView
from dashboard.widgets import FieldGrid, MetricCard, StatusBadge


class RuntimePanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Runtime", parent)
        self._labels = {}
        self._cards = {
            "Application": MetricCard("Application"),
            "Safety": MetricCard("Safety"),
            "Broker": MetricCard("Broker"),
        }
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)
        cards = QHBoxLayout()
        cards.setSpacing(10)
        for card in self._cards.values():
            cards.addWidget(card)
        layout.addLayout(cards)
        grid = FieldGrid(
            (
                "Instruments",
                "Market Data",
                "Journal",
                "Starts",
                "Stops",
                "Restarts",
                "Started At",
                "Stopped At",
                "Last Error",
            )
        )
        layout.addWidget(grid)
        self._labels.update(grid.labels)
        for field in ("Application", "Safety", "Broker"):
            self._labels[field] = self._cards[field].value_label
        self._labels["Market Data"] = StatusBadge()
        self._labels["Journal"] = StatusBadge()
        detail_grid = grid.layout()
        detail_grid.replaceWidget(grid.labels["Market Data"], self._labels["Market Data"])
        grid.labels["Market Data"].deleteLater()
        detail_grid.replaceWidget(grid.labels["Journal"], self._labels["Journal"])
        grid.labels["Journal"].deleteLater()

    def render(self, view: DashboardRuntimeView) -> None:
        self._cards["Application"].set_value(view.application_status)
        self._cards["Safety"].set_value(view.safety_mode)
        self._cards["Broker"].set_value(view.broker_mode)
        self._labels["Instruments"].setText(formatters.joined(view.configured_instruments))
        self._labels["Market Data"].set_status_text(formatters.ready(view.market_data_ready))
        self._labels["Journal"].set_status_text(formatters.ready(view.trade_journal_ready))
        self._labels["Starts"].setText(formatters.integer(view.start_count))
        self._labels["Stops"].setText(formatters.integer(view.stop_count))
        self._labels["Restarts"].setText(formatters.integer(view.restart_count))
        self._labels["Started At"].setText(formatters.timestamp(view.last_started_at))
        self._labels["Stopped At"].setText(formatters.timestamp(view.last_stopped_at))
        self._labels["Last Error"].setText(formatters.text(view.last_error))
