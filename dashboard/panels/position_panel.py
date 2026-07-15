"""
Position dashboard panel.
"""

from PySide6.QtWidgets import QGroupBox, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardPositionView
from dashboard.widgets import FieldGrid, StatusBadge


class PositionPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Position", parent)
        self._labels = {}
        layout = QVBoxLayout(self)
        self._fields = ("Active", "Side", "Quantity", "Average", "Last", "Unrealized", "Realized", "Stop", "Target")
        grid = FieldGrid(self._fields)
        layout.addWidget(grid)
        self._labels.update(grid.labels)
        active = StatusBadge()
        grid.layout().replaceWidget(grid.labels["Active"], active)
        grid.labels["Active"].deleteLater()
        self._labels["Active"] = active

    def render(self, view: DashboardPositionView) -> None:
        values = {
            "Active": "Yes" if view.has_position else "No",
            "Side": view.side,
            "Quantity": formatters.quantity(view.quantity),
            "Average": formatters.price(view.average_price),
            "Last": formatters.price(view.last_price),
            "Unrealized": formatters.price(view.unrealized_pnl),
            "Realized": formatters.price(view.realized_pnl),
            "Stop": formatters.price(view.stop_price),
            "Target": formatters.price(view.target_price),
        }
        for field, value in values.items():
            if field == "Active":
                self._labels[field].set_status_text(value)
            else:
                self._labels[field].setText(formatters.text(value))
