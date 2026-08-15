"""
Trade journal dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardAnalyticsView
from dashboard.models import DashboardJournalView
from dashboard.panels.analytics_panel import AnalyticsPanel
from dashboard.widgets import FieldGrid, StatusBadge, set_label_text


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
                "Trade Source",
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
        self._analytics_panel = AnalyticsPanel()
        layout.addWidget(self._analytics_panel)

    def render(self, view: DashboardJournalView) -> None:
        self._labels["Status"].set_status_text(view.status)
        set_label_text(self._labels["Records"], formatters.integer(view.records))
        set_label_text(self._labels["Message"], view.message)
        set_label_text(self._labels["Trade ID"], view.latest_trade_id)
        set_label_text(self._labels["Trade Source"], view.latest_trade_source)
        set_label_text(self._labels["Instrument"], view.latest_instrument)
        set_label_text(self._labels["Side"], view.latest_side)
        set_label_text(self._labels["Quantity"], formatters.quantity(view.latest_quantity))
        set_label_text(self._labels["Entry"], formatters.price(view.latest_entry_price))
        set_label_text(self._labels["Exit"], formatters.price(view.latest_exit_price))
        set_label_text(self._labels["Exit Type"], view.latest_exit_type)
        set_label_text(self._labels["Realized P&L"], formatters.price(view.latest_realized_pnl))
        set_label_text(self._labels["Opened"], formatters.timestamp(view.latest_opened_at))
        set_label_text(self._labels["Closed"], formatters.timestamp(view.latest_closed_at))
        set_label_text(self._labels["Holding Time"], formatters.integer(view.latest_holding_seconds))
        set_label_text(self._labels["MFE"], formatters.price(view.latest_mfe))
        set_label_text(self._labels["MAE"], formatters.price(view.latest_mae))
        set_label_text(self._labels["Daily P&L"], formatters.price(view.daily_pnl))
        set_label_text(self._labels["Wins"], formatters.integer(view.wins))
        set_label_text(self._labels["Losses"], formatters.integer(view.losses))
        set_label_text(self._labels["Win Rate"], formatters.ratio(view.win_rate))
        set_label_text(self._labels["Profit Factor"], formatters.ratio(view.profit_factor))

    def render_analytics(self, view: DashboardAnalyticsView) -> None:
        self._analytics_panel.render(view)
