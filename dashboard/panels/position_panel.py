"""
Position dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardPositionView
from dashboard.widgets import FieldGrid, StatusBadge


class PositionPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Position", parent)
        self._labels = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)
        self._fields = (
            "Status",
            "Active",
            "Side",
            "Quantity",
            "Average",
            "Last",
            "Unrealized",
            "Realized",
            "Entry",
            "Stop",
            "Target",
            "Valid Until",
            "Plan ID",
            "Opened",
            "Closed",
            "Exit Type",
            "MFE",
            "MAE",
        )
        grid = FieldGrid(self._fields)
        layout.addWidget(grid)
        self._labels.update(grid.labels)
        for field in ("Status", "Active"):
            badge = StatusBadge()
            grid.layout().replaceWidget(grid.labels[field], badge)
            grid.labels[field].deleteLater()
            self._labels[field] = badge

    def render(self, view: DashboardPositionView) -> None:
        values = {
            "Status": view.status,
            "Active": "Yes" if view.has_position else "No",
            "Side": view.side,
            "Quantity": formatters.quantity(view.quantity),
            "Average": formatters.price(view.average_price),
            "Last": formatters.price(view.last_price),
            "Unrealized": formatters.price(view.unrealized_pnl),
            "Realized": formatters.price(view.realized_pnl),
            "Entry": formatters.price(view.entry_price),
            "Stop": formatters.price(view.stop_price),
            "Target": formatters.price(view.target_price),
            "Valid Until": formatters.timestamp(view.valid_until),
            "Plan ID": formatters.text(view.plan_id),
            "Opened": formatters.timestamp(view.opened_at),
            "Closed": formatters.timestamp(view.closed_at),
            "Exit Type": formatters.text(view.exit_type),
            "MFE": formatters.price(view.mfe),
            "MAE": formatters.price(view.mae),
        }
        for field, value in values.items():
            if field in ("Status", "Active"):
                self._labels[field].set_status_text(value)
            else:
                self._labels[field].setText(formatters.text(value))
