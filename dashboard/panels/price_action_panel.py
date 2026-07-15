"""
Read-only price-action evidence dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardPriceActionView
from dashboard.widgets import FieldGrid, MetricCard, StatusBadge


class PriceActionPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Price Action", parent)
        self._labels = {}
        self._cards = {
            "Trend": MetricCard("Trend"),
            "Structure": MetricCard("Structure"),
            "BOS": MetricCard("Break Of Structure"),
            "CHoCH": MetricCard("Change Of Character"),
        }
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 18, 14, 14)
        root.setSpacing(12)
        root.setAlignment(Qt.AlignTop)
        cards = QHBoxLayout()
        cards.setSpacing(10)
        for card in self._cards.values():
            cards.addWidget(card)
        root.addLayout(cards)

        fields = (
            "Available",
            "Symbol",
            "Higher High",
            "Higher Low",
            "Lower High",
            "Lower Low",
            "Swing High",
            "Swing Low",
            "Pullback",
            "Range",
            "Liquidity Sweep",
            "Updated Time",
        )
        grid = FieldGrid(fields)
        root.addWidget(grid)
        self._labels.update(grid.labels)
        for field in ("Available", "Pullback", "Range", "Liquidity Sweep"):
            badge = StatusBadge()
            grid.layout().replaceWidget(grid.labels[field], badge)
            grid.labels[field].deleteLater()
            self._labels[field] = badge
        for field, card in self._cards.items():
            self._labels[field] = card.value_label

    def render(self, view: DashboardPriceActionView) -> None:
        if not isinstance(view, DashboardPriceActionView):
            raise TypeError("view must be DashboardPriceActionView")
        self._cards["Trend"].set_value(view.trend)
        self._cards["Structure"].set_value(view.market_structure)
        self._cards["BOS"].set_value(view.bos_direction)
        self._cards["CHoCH"].set_value(view.choch_direction)
        values = {
            "Available": formatters.yes_no(view.available),
            "Symbol": view.symbol,
            "Higher High": formatters.price(view.latest_hh),
            "Higher Low": formatters.price(view.latest_hl),
            "Lower High": formatters.price(view.latest_lh),
            "Lower Low": formatters.price(view.latest_ll),
            "Swing High": formatters.price(view.swing_high),
            "Swing Low": formatters.price(view.swing_low),
            "Pullback": view.pullback_state,
            "Range": view.range_state,
            "Liquidity Sweep": view.liquidity_sweep,
            "Updated Time": formatters.timestamp(view.updated_at),
        }
        for field, value in values.items():
            if isinstance(self._labels[field], StatusBadge):
                self._labels[field].set_status_text(value)
            else:
                self._labels[field].setText(formatters.text(value))
