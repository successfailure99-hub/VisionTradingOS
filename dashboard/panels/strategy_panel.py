"""
Strategy and risk dashboard panel.
"""

from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel

from dashboard.models import DashboardStrategyView


class StrategyPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Strategy", parent)
        self._labels = {}
        layout = QGridLayout(self)
        self._fields = (
            "Decision", "Direction", "Setup", "Entry", "Stop",
            "Target", "Block", "Risk", "Approved Qty",
            "Risk Amount", "Reward/Risk", "Order",
        )
        for row, field in enumerate(self._fields):
            layout.addWidget(QLabel(field), row, 0)
            label = QLabel("-")
            layout.addWidget(label, row, 1)
            self._labels[field] = label

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
            "Approved Qty": _quantity(view.approved_quantity),
            "Risk Amount": _price(view.risk_amount),
            "Reward/Risk": _number(view.reward_risk),
            "Order": view.latest_order_status,
        }
        for field, value in values.items():
            self._labels[field].setText(_text(value))


def _quantity(value) -> str:
    return str(value) if value is not None else "-"


def _price(value) -> str:
    return f"{value:.2f}" if value is not None else "-"


def _number(value) -> str:
    return f"{value:.4f}" if value is not None else "-"


def _text(value) -> str:
    return str(value) if value not in (None, "") else "-"
