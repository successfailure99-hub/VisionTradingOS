"""
Strategy and risk dashboard panel.
"""

from PySide6.QtWidgets import QGroupBox, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardStrategyView
from dashboard.widgets import FieldGrid, StatusBadge


class StrategyPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Strategy", parent)
        self._labels = {}
        layout = QVBoxLayout(self)
        self._fields = (
            "Decision", "Direction", "Setup", "Entry", "Stop",
            "Target", "Block", "Risk", "Approved Qty",
            "Risk Amount", "Reward/Risk", "Order",
        )
        grid = FieldGrid(self._fields)
        layout.addWidget(grid)
        self._labels.update(grid.labels)
        for field in ("Decision", "Risk", "Order"):
            badge = StatusBadge()
            grid.layout().replaceWidget(grid.labels[field], badge)
            grid.labels[field].deleteLater()
            self._labels[field] = badge

    def render(self, view: DashboardStrategyView) -> None:
        values = {
            "Decision": view.decision,
            "Direction": view.direction,
            "Setup": view.setup_quality,
            "Entry": view.entry_reference,
            "Stop": view.stop_reference,
            "Target": view.target_reference,
            "Block": view.block_reason,
            "Risk": view.risk_decision,
            "Approved Qty": formatters.quantity(view.approved_quantity),
            "Risk Amount": formatters.price(view.risk_amount),
            "Reward/Risk": formatters.ratio(view.reward_risk),
            "Order": view.latest_order_status,
        }
        for field, value in values.items():
            if isinstance(self._labels[field], StatusBadge):
                self._labels[field].set_status_text(value)
            else:
                self._labels[field].setText(formatters.text(value))
