"""
Trade journal dashboard panel.
"""

from PySide6.QtWidgets import QGroupBox, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardJournalView
from dashboard.widgets import FieldGrid


class JournalPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Journal", parent)
        self._labels = {}
        layout = QVBoxLayout(self)
        grid = FieldGrid(("Trade ID", "Exit Type", "Realized P&L", "Opened", "Closed"))
        layout.addWidget(grid)
        self._labels.update(grid.labels)

    def render(self, view: DashboardJournalView) -> None:
        self._labels["Trade ID"].setText(formatters.text(view.latest_trade_id))
        self._labels["Exit Type"].setText(formatters.text(view.latest_exit_type))
        self._labels["Realized P&L"].setText(formatters.price(view.latest_realized_pnl))
        self._labels["Opened"].setText(formatters.timestamp(view.latest_opened_at))
        self._labels["Closed"].setText(formatters.timestamp(view.latest_closed_at))
