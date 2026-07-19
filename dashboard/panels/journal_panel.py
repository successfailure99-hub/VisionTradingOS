"""
Trade journal dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardJournalView
from dashboard.widgets import FieldGrid, StatusBadge


class JournalPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Journal", parent)
        self._labels = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)
        grid = FieldGrid(
            (
                "Status",
                "Records",
                "Message",
                "Trade ID",
                "Instrument",
                "Side",
                "Quantity",
                "Entry",
                "Exit",
                "Exit Type",
                "Realized P&L",
                "Opened",
                "Closed",
                "Holding Time",
                "MFE",
                "MAE",
                "Daily P&L",
                "Wins",
                "Losses",
                "Win Rate",
                "Profit Factor",
            )
        )
        layout.addWidget(grid)
        self._labels.update(grid.labels)
        status = StatusBadge()
        grid.layout().replaceWidget(grid.labels["Status"], status)
        grid.labels["Status"].deleteLater()
        self._labels["Status"] = status

    def render(self, view: DashboardJournalView) -> None:
        self._labels["Status"].set_status_text(view.status)
        self._labels["Records"].setText(formatters.integer(view.records))
        self._labels["Message"].setText(formatters.text(view.message))
        self._labels["Trade ID"].setText(formatters.text(view.latest_trade_id))
        self._labels["Instrument"].setText(formatters.text(view.latest_instrument))
        self._labels["Side"].setText(formatters.text(view.latest_side))
        self._labels["Quantity"].setText(formatters.quantity(view.latest_quantity))
        self._labels["Entry"].setText(formatters.price(view.latest_entry_price))
        self._labels["Exit"].setText(formatters.price(view.latest_exit_price))
        self._labels["Exit Type"].setText(formatters.text(view.latest_exit_type))
        self._labels["Realized P&L"].setText(formatters.price(view.latest_realized_pnl))
        self._labels["Opened"].setText(formatters.timestamp(view.latest_opened_at))
        self._labels["Closed"].setText(formatters.timestamp(view.latest_closed_at))
        self._labels["Holding Time"].setText(formatters.integer(view.latest_holding_seconds))
        self._labels["MFE"].setText(formatters.price(view.latest_mfe))
        self._labels["MAE"].setText(formatters.price(view.latest_mae))
        self._labels["Daily P&L"].setText(formatters.price(view.daily_pnl))
        self._labels["Wins"].setText(formatters.integer(view.wins))
        self._labels["Losses"].setText(formatters.integer(view.losses))
        self._labels["Win Rate"].setText(formatters.ratio(view.win_rate))
        self._labels["Profit Factor"].setText(formatters.ratio(view.profit_factor))
