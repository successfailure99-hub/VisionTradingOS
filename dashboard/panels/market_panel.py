"""
Market dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardMarketView
from dashboard.widgets import FieldGrid, MetricCard, StatusBadge


class MarketPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Market", parent)
        self._labels = {}
        self._cards = {
            "Last": MetricCard("Last"),
            "Bid": MetricCard("Bid"),
            "Ask": MetricCard("Ask"),
        }
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)
        cards = QHBoxLayout()
        cards.setSpacing(10)
        for card in self._cards.values():
            cards.addWidget(card)
        layout.addLayout(cards)
        self._fields = (
            "Symbol", "Timeframe", "Status",
            "Session High", "Session Low", "Candle O", "Candle H",
            "Candle L", "Candle C", "VWAP", "VWAP Source", "VWAP Type",
            "VWAP Venue", "VWAP Expiry", "VWAP Volume", "VWAP Source Price", "CPR Pivot", "CPR BC",
            "CPR TC", "Cam H3", "Cam H4", "Cam H5", "Cam H6",
            "Cam L3", "Cam L4", "Cam L5", "Cam L6", "Bias",
            "Phase", "Strength", "Options", "Updated",
        )
        grid = FieldGrid(self._fields)
        layout.addWidget(grid)
        self._labels.update(grid.labels)
        for field, card in self._cards.items():
            self._labels[field] = card.value_label
        status = StatusBadge()
        grid.layout().replaceWidget(grid.labels["Status"], status)
        grid.labels["Status"].deleteLater()
        self._labels["Status"] = status

    def render(self, view: DashboardMarketView) -> None:
        self._cards["Last"].set_value(formatters.price(view.last_price))
        self._cards["Bid"].set_value(formatters.price(view.bid_price))
        self._cards["Ask"].set_value(formatters.price(view.ask_price))
        values = {
            "Symbol": view.symbol,
            "Timeframe": view.timeframe,
            "Status": view.runtime_status,
            "Session High": formatters.price(view.session_high),
            "Session Low": formatters.price(view.session_low),
            "Candle O": formatters.price(view.latest_candle_open),
            "Candle H": formatters.price(view.latest_candle_high),
            "Candle L": formatters.price(view.latest_candle_low),
            "Candle C": formatters.price(view.latest_candle_close),
            "VWAP": formatters.price(view.vwap),
            "VWAP Source": view.vwap_source,
            "VWAP Type": view.vwap_source_type,
            "VWAP Venue": view.vwap_source_exchange,
            "VWAP Expiry": formatters.date_text(view.vwap_source_expiry),
            "VWAP Volume": formatters.integer(view.vwap_source_volume),
            "VWAP Source Price": formatters.price(view.vwap_source_price),
            "CPR Pivot": formatters.price(view.cpr_pivot),
            "CPR BC": formatters.price(view.cpr_bc),
            "CPR TC": formatters.price(view.cpr_tc),
            "Cam H3": formatters.price(view.camarilla_h3),
            "Cam H4": formatters.price(view.camarilla_h4),
            "Cam H5": formatters.price(view.camarilla_h5),
            "Cam H6": formatters.price(view.camarilla_h6),
            "Cam L3": formatters.price(view.camarilla_l3),
            "Cam L4": formatters.price(view.camarilla_l4),
            "Cam L5": formatters.price(view.camarilla_l5),
            "Cam L6": formatters.price(view.camarilla_l6),
            "Bias": view.market_bias,
            "Phase": view.market_phase,
            "Strength": view.context_strength,
            "Options": view.option_chain_direction,
            "Updated": formatters.timestamp(view.updated_at),
        }
        for field, value in values.items():
            if isinstance(self._labels[field], StatusBadge):
                self._labels[field].set_status_text(value)
            else:
                self._labels[field].setText(formatters.text(value))
