"""
Read-only performance analytics dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QGroupBox, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout

from dashboard.models import DashboardAnalyticsView
from dashboard.widgets import MetricCard, StatusBadge


class AnalyticsPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Analytics", parent)
        self._cards = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)

        self._status = StatusBadge()
        layout.addWidget(self._status, 0, Qt.AlignLeft)

        self._metrics = QGridLayout()
        self._metrics.setHorizontalSpacing(10)
        self._metrics.setVerticalSpacing(10)
        layout.addLayout(self._metrics)

        self._recent = _table(("Trade", "Instrument", "Side", "Net P&L", "Exit"))
        self._equity = _table(("Seq", "Trade", "Cumulative", "Drawdown"))
        self._periods = _table(("Period", "Trades", "Net P&L", "Win Rate"))
        self._setups = _table(("Setup", "Trades", "Net P&L", "Win Rate"))
        self._time = _table(("Time Bucket", "Trades", "Net P&L", "Win Rate"))
        for table in (self._recent, self._equity, self._periods, self._setups, self._time):
            layout.addWidget(table)

    def render(self, view: DashboardAnalyticsView) -> None:
        self._status.set_status_text(view.status)
        for index, metric in enumerate(view.metric_cards):
            card = self._cards.get(metric.label)
            if card is None:
                card = MetricCard(metric.label)
                self._cards[metric.label] = card
                self._metrics.addWidget(card, index // 4, index % 4)
            card.set_value(metric.value, kind=metric.kind)
        _fill(self._recent, view.recent_trades)
        _fill(self._equity, view.equity_curve)
        _fill(self._periods, view.period_performance)
        _fill(self._setups, view.setup_statistics)
        _fill(self._time, view.time_of_day_statistics)


def _table(headers: tuple[str, ...]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionMode(QTableWidget.NoSelection)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.setMinimumHeight(120)
    return table


def _fill(table: QTableWidget, rows) -> None:
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row.columns):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row_index, column_index, item)
