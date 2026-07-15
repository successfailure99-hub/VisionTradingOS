"""
Read-only option-chain analytics dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QGroupBox, QHBoxLayout, QTableWidget, QTableWidgetItem, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardOptionChainStrikeView, DashboardOptionChainView
from dashboard.widgets import FieldGrid, MetricCard, StatusBadge


STRIKE_COLUMNS = (
    "Call Bid",
    "Call Ask",
    "Call LTP",
    "Call Volume",
    "Call Change OI",
    "Call OI",
    "Strike",
    "Put OI",
    "Put Change OI",
    "Put Volume",
    "Put LTP",
    "Put Bid",
    "Put Ask",
)


class OptionChainPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Option Chain Analytics", parent)
        self._labels = {}
        self._cards = {
            "Positioning Bias": MetricCard("Positioning Bias"),
            "OI PCR": MetricCard("OI PCR"),
            "Change OI PCR": MetricCard("Change OI PCR"),
            "ATM Strike": MetricCard("ATM Strike"),
        }
        self._table = QTableWidget(0, len(STRIKE_COLUMNS))
        self._table.setHorizontalHeaderLabels(STRIKE_COLUMNS)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setContextMenuPolicy(Qt.NoContextMenu)
        self._table.setAlternatingRowColors(True)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        cards = QHBoxLayout()
        for card in self._cards.values():
            cards.addWidget(card)
        root.addLayout(cards)

        fields = (
            "Available",
            "Symbol",
            "Exchange",
            "Expiry",
            "Timestamp",
            "Underlying",
            "Strike Count",
            "Call Pressure",
            "Put Pressure",
            "Support",
            "Resistance",
            "Max Pain",
            "Max Call OI",
            "Max Put OI",
            "Max Call Change OI",
            "Max Put Change OI",
            "Total Call OI",
            "Total Put OI",
            "Total Call Change OI",
            "Total Put Change OI",
        )
        grid = FieldGrid(fields)
        root.addWidget(grid)
        self._labels.update(grid.labels)
        for field in ("Available", "Call Pressure", "Put Pressure"):
            badge = StatusBadge()
            grid.layout().replaceWidget(grid.labels[field], badge)
            grid.labels[field].deleteLater()
            self._labels[field] = badge
        for field, card in self._cards.items():
            self._labels[field] = card.value_label

        root.addWidget(self._table, 1)

    def render(self, view: DashboardOptionChainView) -> None:
        if not isinstance(view, DashboardOptionChainView):
            raise TypeError("view must be DashboardOptionChainView")
        self._cards["Positioning Bias"].set_value(view.positioning_bias)
        self._cards["OI PCR"].set_value(formatters.ratio(view.oi_pcr), kind="neutral")
        self._cards["Change OI PCR"].set_value(formatters.ratio(view.change_oi_pcr), kind="neutral")
        self._cards["ATM Strike"].set_value(formatters.price(view.atm_strike), kind="neutral")
        self._labels["Available"].set_status_text(formatters.yes_no(view.available))
        self._labels["Symbol"].setText(formatters.text(view.symbol))
        self._labels["Exchange"].setText(formatters.text(view.exchange))
        self._labels["Expiry"].setText(formatters.date_text(view.expiry_date))
        self._labels["Timestamp"].setText(formatters.timestamp(view.timestamp))
        self._labels["Underlying"].setText(formatters.price(view.underlying_price))
        self._labels["Strike Count"].setText(formatters.integer(view.strike_count))
        self._labels["Call Pressure"].set_status_text(view.call_pressure, kind=_pressure_kind(view.call_pressure))
        self._labels["Put Pressure"].set_status_text(view.put_pressure, kind=_pressure_kind(view.put_pressure))
        self._labels["Support"].setText(formatters.price(view.support_strike))
        self._labels["Resistance"].setText(formatters.price(view.resistance_strike))
        self._labels["Max Pain"].setText(formatters.price(view.max_pain_strike))
        self._labels["Max Call OI"].setText(_strike_metric(view.max_call_oi_strike, view.max_call_oi_value))
        self._labels["Max Put OI"].setText(_strike_metric(view.max_put_oi_strike, view.max_put_oi_value))
        self._labels["Max Call Change OI"].setText(_strike_metric(view.max_call_change_oi_strike, view.max_call_change_oi_value))
        self._labels["Max Put Change OI"].setText(_strike_metric(view.max_put_change_oi_strike, view.max_put_change_oi_value))
        self._labels["Total Call OI"].setText(formatters.integer(view.total_call_oi))
        self._labels["Total Put OI"].setText(formatters.integer(view.total_put_oi))
        self._labels["Total Call Change OI"].setText(formatters.integer(view.total_call_change_oi))
        self._labels["Total Put Change OI"].setText(formatters.integer(view.total_put_change_oi))
        self._render_strikes(view)

    def _render_strikes(self, view: DashboardOptionChainView) -> None:
        rows = select_display_strikes(view)
        self._table.setRowCount(len(rows))
        for row, strike in enumerate(rows):
            values = (
                formatters.price(strike.call_bid_price),
                formatters.price(strike.call_ask_price),
                formatters.price(strike.call_last_price),
                formatters.integer(strike.call_volume),
                formatters.integer(strike.call_change_open_interest),
                formatters.integer(strike.call_open_interest),
                formatters.price(strike.strike_price),
                formatters.integer(strike.put_open_interest),
                formatters.integer(strike.put_change_open_interest),
                formatters.integer(strike.put_volume),
                formatters.price(strike.put_last_price),
                formatters.price(strike.put_bid_price),
                formatters.price(strike.put_ask_price),
            )
            row_tags = _row_tags(view, strike)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setData(Qt.UserRole, row_tags)
                if row_tags:
                    item.setBackground(_row_color(row_tags))
                if STRIKE_COLUMNS[column] in {"Call Change OI", "Put Change OI"}:
                    _style_change_item(item, value)
                self._table.setItem(row, column, item)
        self._table.resizeColumnsToContents()


def select_display_strikes(view: DashboardOptionChainView, wing_size: int = 10) -> tuple[DashboardOptionChainStrikeView, ...]:
    rows = tuple(sorted(view.strikes, key=lambda strike: strike.strike_price))
    if not rows or view.atm_strike is None:
        return rows
    atm_index = next((index for index, strike in enumerate(rows) if strike.strike_price == view.atm_strike), None)
    if atm_index is None:
        atm_index = min(range(len(rows)), key=lambda index: (abs(rows[index].strike_price - view.atm_strike), rows[index].strike_price))
    selected = set(rows[max(0, atm_index - wing_size): atm_index + wing_size + 1])
    special_prices = {
        view.support_strike,
        view.resistance_strike,
        view.max_pain_strike,
        view.max_call_oi_strike,
        view.max_put_oi_strike,
        view.max_call_change_oi_strike,
        view.max_put_change_oi_strike,
    }
    selected.update(strike for strike in rows if strike.strike_price in special_prices)
    return tuple(sorted(selected, key=lambda strike: strike.strike_price))


def _strike_metric(strike_price: float | None, value: int | None) -> str:
    if strike_price is None or value is None:
        return formatters.MISSING
    return f"{formatters.price(strike_price)} / {formatters.integer(value)}"


def _pressure_kind(value: str) -> str:
    key = value.strip().lower().replace(" ", "_")
    if key in {"call_writing", "put_writing"}:
        return "positive"
    if key in {"call_unwinding", "put_unwinding"}:
        return "negative"
    if key in {"balanced", "-"}:
        return "neutral"
    return "warning"


def _row_tags(view: DashboardOptionChainView, strike: DashboardOptionChainStrikeView) -> str:
    tags = []
    if strike.is_atm:
        tags.append("atm")
    if view.support_strike == strike.strike_price:
        tags.append("support")
    if view.resistance_strike == strike.strike_price:
        tags.append("resistance")
    if view.max_pain_strike == strike.strike_price:
        tags.append("max-pain")
    return " ".join(tags)


def _row_color(tags: str) -> QColor:
    if "atm" in tags:
        return QColor(34, 83, 113)
    if "support" in tags:
        return QColor(29, 78, 58)
    if "resistance" in tags:
        return QColor(91, 57, 45)
    if "max-pain" in tags:
        return QColor(72, 63, 96)
    return QColor(21, 27, 33)


def _style_change_item(item: QTableWidgetItem, value: str) -> None:
    try:
        number = int(value)
    except ValueError:
        item.setData(Qt.UserRole + 1, "neutral")
        return
    if number > 0:
        item.setForeground(QColor(126, 226, 168))
        item.setData(Qt.UserRole + 1, "positive")
    elif number < 0:
        item.setForeground(QColor(255, 139, 139))
        item.setData(Qt.UserRole + 1, "negative")
    else:
        item.setData(Qt.UserRole + 1, "neutral")
