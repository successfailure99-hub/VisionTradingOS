"""
Position dashboard panel.
"""

from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel

from dashboard.models import DashboardPositionView


class PositionPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Position", parent)
        self._labels = {}
        layout = QGridLayout(self)
        self._fields = ("Active", "Side", "Quantity", "Average", "Last", "Unrealized", "Realized", "Stop", "Target")
        for row, field in enumerate(self._fields):
            layout.addWidget(QLabel(field), row, 0)
            label = QLabel("-")
            layout.addWidget(label, row, 1)
            self._labels[field] = label

    def render(self, view: DashboardPositionView) -> None:
        values = {
            "Active": "Yes" if view.has_position else "No",
            "Side": view.side,
            "Quantity": _quantity(view.quantity),
            "Average": _price(view.average_price),
            "Last": _price(view.last_price),
            "Unrealized": _price(view.unrealized_pnl),
            "Realized": _price(view.realized_pnl),
            "Stop": _price(view.stop_price),
            "Target": _price(view.target_price),
        }
        for field, value in values.items():
            self._labels[field].setText(_text(value))


def _quantity(value) -> str:
    return str(value) if value is not None else "-"


def _price(value) -> str:
    return f"{value:.2f}" if value is not None else "-"


def _text(value) -> str:
    return str(value) if value not in (None, "") else "-"
