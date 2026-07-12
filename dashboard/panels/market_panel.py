"""
Market dashboard panel.
"""

from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel

from dashboard.models import DashboardMarketView


class MarketPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Market", parent)
        self._labels = {}
        layout = QGridLayout(self)
        self._fields = (
            "Symbol", "Timeframe", "Status", "Last", "Bid", "Ask",
            "Session High", "Session Low", "Candle O", "Candle H",
            "Candle L", "Candle C", "VWAP", "CPR Pivot", "CPR BC",
            "CPR TC", "Cam H3", "Cam H4", "Cam H5", "Cam H6",
            "Cam L3", "Cam L4", "Cam L5", "Cam L6", "Bias",
            "Phase", "Strength", "Options", "Updated",
        )
        for row, field in enumerate(self._fields):
            layout.addWidget(QLabel(field), row, 0)
            label = QLabel("-")
            layout.addWidget(label, row, 1)
            self._labels[field] = label

    def render(self, view: DashboardMarketView) -> None:
        values = {
            "Symbol": view.symbol,
            "Timeframe": view.timeframe,
            "Status": view.runtime_status,
            "Last": _price(view.last_price),
            "Bid": _price(view.bid_price),
            "Ask": _price(view.ask_price),
            "Session High": _price(view.session_high),
            "Session Low": _price(view.session_low),
            "Candle O": _price(view.latest_candle_open),
            "Candle H": _price(view.latest_candle_high),
            "Candle L": _price(view.latest_candle_low),
            "Candle C": _price(view.latest_candle_close),
            "VWAP": _price(view.vwap),
            "CPR Pivot": _price(view.cpr_pivot),
            "CPR BC": _price(view.cpr_bc),
            "CPR TC": _price(view.cpr_tc),
            "Cam H3": _price(view.camarilla_h3),
            "Cam H4": _price(view.camarilla_h4),
            "Cam H5": _price(view.camarilla_h5),
            "Cam H6": _price(view.camarilla_h6),
            "Cam L3": _price(view.camarilla_l3),
            "Cam L4": _price(view.camarilla_l4),
            "Cam L5": _price(view.camarilla_l5),
            "Cam L6": _price(view.camarilla_l6),
            "Bias": view.market_bias,
            "Phase": view.market_phase,
            "Strength": view.context_strength,
            "Options": view.option_chain_direction,
            "Updated": _timestamp(view.updated_at),
        }
        for field, value in values.items():
            self._labels[field].setText(_text(value))


def _price(value) -> str:
    return f"{value:.2f}" if value is not None else "-"


def _text(value) -> str:
    return str(value) if value not in (None, "") else "-"


def _timestamp(value) -> str:
    return value.isoformat(sep=" ", timespec="seconds") if value is not None else "-"
