"""
Trade journal dashboard panel.
"""

from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel

from dashboard.models import DashboardJournalView


class JournalPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Journal", parent)
        self._labels = {}
        layout = QGridLayout(self)
        for row, field in enumerate(("Trade ID", "Exit Type", "Realized P&L", "Opened", "Closed")):
            layout.addWidget(QLabel(field), row, 0)
            label = QLabel("-")
            layout.addWidget(label, row, 1)
            self._labels[field] = label

    def render(self, view: DashboardJournalView) -> None:
        self._labels["Trade ID"].setText(_text(view.latest_trade_id))
        self._labels["Exit Type"].setText(_text(view.latest_exit_type))
        self._labels["Realized P&L"].setText(_price(view.latest_realized_pnl))
        self._labels["Opened"].setText(_timestamp(view.latest_opened_at))
        self._labels["Closed"].setText(_timestamp(view.latest_closed_at))


def _price(value) -> str:
    return f"{value:.2f}" if value is not None else "-"


def _text(value) -> str:
    return str(value) if value not in (None, "") else "-"


def _timestamp(value) -> str:
    return value.isoformat(sep=" ", timespec="seconds") if value is not None else "-"
