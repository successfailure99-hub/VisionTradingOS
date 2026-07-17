"""
Strategy and risk dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardStrategyView
from dashboard.widgets import FieldGrid, StatusBadge


class StrategyPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Strategy", parent)
        self._labels = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)
        self._fields = (
            "Decision", "Direction", "Setup", "Entry", "Stop",
            "Target", "Block", "Risk", "Approved Qty",
            "Risk Amount", "Reward/Risk", "Entry Price", "Stop Price",
            "Target Price", "Lot Size", "Approved Lots", "Plan Status",
            "Plan Valid Until", "Risk Reason", "Trade Plan",
        )
        grid = FieldGrid(self._fields)
        layout.addWidget(grid)
        self._labels.update(grid.labels)
        for field in ("Decision", "Risk", "Trade Plan"):
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
            "Entry Price": formatters.price(view.entry_price),
            "Stop Price": formatters.price(view.stop_price),
            "Target Price": formatters.price(view.target_price),
            "Lot Size": formatters.quantity(view.lot_size),
            "Approved Lots": formatters.quantity(view.approved_lots),
            "Plan Status": view.plan_status,
            "Plan Valid Until": formatters.timestamp(view.plan_valid_until),
            "Risk Reason": view.risk_reason,
            "Trade Plan": view.latest_order_status,
        }
        for field, value in values.items():
            if isinstance(self._labels[field], StatusBadge):
                self._labels[field].set_status_text(value)
            else:
                self._labels[field].setText(formatters.text(value))
