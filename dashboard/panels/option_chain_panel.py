"""
Read-only option-chain analytics dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

from dashboard import formatters
from dashboard.models import DashboardOptionChainStrikeView, DashboardOptionChainView
from dashboard.widgets import MetricCard


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

RUNTIME_TABLE_COLUMNS = ("Instrument", "State", "Expiry", "Contracts", "Option Ticks", "Last Update", "Last Error")
EVENT_TABLE_COLUMNS = ("Timestamp", "Instrument", "State", "Message")


class ResponsiveMetricGrid(QWidget):
    def __init__(self, fields: tuple[str, ...], cards: dict[str, MetricCard], *, max_columns: int = 4, parent=None):
        super().__init__(parent)
        self._fields = tuple(fields)
        self._cards = cards
        self._max_columns = max_columns
        self._columns = 0
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(10)
        self._layout.setVerticalSpacing(10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._relayout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _target_columns(self) -> int:
        width = max(self.width(), 1)
        if self._max_columns >= 4 and width >= 920:
            return 4
        if width >= 560:
            return min(2, self._max_columns)
        return 1

    def _relayout(self) -> None:
        columns = self._target_columns()
        if columns == self._columns:
            return
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
        self._columns = columns
        for column in range(max(self._max_columns, 4)):
            self._layout.setColumnStretch(column, 0)
        for column in range(columns):
            self._layout.setColumnStretch(column, 1)
        for index, field in enumerate(self._fields):
            row, column = divmod(index, columns)
            card = self._cards[field]
            card.setParent(self)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            self._layout.addWidget(card, row, column)


class OptionChainPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Option Chain Analytics", parent)
        self._labels = {}
        self._overview_fields = (
            "Status",
            "Available",
            "Underlying",
            "Expiry",
            "ATM Strike",
            "Last Update",
            "Positioning Bias",
            "OI PCR",
            "Change OI PCR",
            "Max Pain",
            "Support",
            "Resistance",
            "Call Pressure",
            "Put Pressure",
            "Total Call OI",
            "Total Put OI",
            "Total Call Change OI",
            "Total Put Change OI",
            "Max Call OI",
            "Max Put OI",
            "Max Call Change OI",
            "Max Put Change OI",
        )
        self._diagnostic_fields = (
            "Message",
            "Enabled",
            "Configured",
            "Started",
            "Runtime State",
            "Last Error",
            "Current Spot",
            "Nearest Expiry",
            "Resolved ATM",
            "Contracts Resolved",
            "Contracts Active",
            "Contracts Total",
            "Last Underlying",
            "Spot Ticks",
            "Option Ticks",
            "Last Spot Tick",
            "Last Option Tick",
            "Analytics Updated",
            "Market Feed",
            "Spot Feed",
            "Discovery",
            "Subscription",
            "Option Feed",
            "Analytics",
            "Dashboard",
            "Symbol",
            "Exchange",
            "Timestamp",
            "Strike Count",
        )
        self._cards = {field: MetricCard(field) for field in self._overview_fields + self._diagnostic_fields}
        self._overview_cards = {field: self._cards[field] for field in self._overview_fields}
        self._diagnostic_cards = {field: self._cards[field] for field in self._diagnostic_fields}
        for field in ("Message", "Last Error"):
            self._cards[field].setMinimumHeight(96)
        for field, card in self._cards.items():
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            self._labels[field] = card.value_label

        self._runtime_table = self._table_widget(RUNTIME_TABLE_COLUMNS)
        self._event_table = self._table_widget(EVENT_TABLE_COLUMNS)
        self._event_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table = self._table_widget(STRIKE_COLUMNS)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setDefaultSectionSize(30)
        self._table.horizontalHeader().setMinimumHeight(34)
        self._table.setMinimumHeight(260)
        self._empty_chain = QLabel(formatters.MISSING)
        self._empty_chain.setProperty("role", "field-value")
        self._empty_chain.setAlignment(Qt.AlignCenter)
        self._empty_chain.setWordWrap(True)
        self._empty_chain.setMinimumHeight(36)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 18, 14, 14)
        root.setSpacing(12)
        self._tabs = QTabWidget()
        self._tabs.addTab(self._overview_tab(), "Overview")
        self._tabs.addTab(self._diagnostics_tab(), "Diagnostics")
        self._tabs.addTab(self._chain_tab(), "Chain")
        root.addWidget(self._tabs, 1)

    def _overview_tab(self) -> QScrollArea:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(ResponsiveMetricGrid(self._overview_fields[:6], self._overview_cards, max_columns=4))
        layout.addWidget(ResponsiveMetricGrid(self._overview_fields[6:], self._overview_cards, max_columns=4))
        layout.addStretch(1)
        return _scroll(content)

    def _diagnostics_tab(self) -> QScrollArea:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(ResponsiveMetricGrid(self._diagnostic_fields[:6], self._diagnostic_cards, max_columns=2))
        layout.addWidget(ResponsiveMetricGrid(self._diagnostic_fields[6:13], self._diagnostic_cards, max_columns=2))
        layout.addWidget(ResponsiveMetricGrid(self._diagnostic_fields[13:18], self._diagnostic_cards, max_columns=2))
        layout.addWidget(ResponsiveMetricGrid(self._diagnostic_fields[18:25], self._diagnostic_cards, max_columns=4))
        layout.addWidget(ResponsiveMetricGrid(self._diagnostic_fields[25:], self._diagnostic_cards, max_columns=2))
        layout.addWidget(self._runtime_table)
        layout.addWidget(self._event_table)
        layout.addStretch(1)
        return _scroll(content)

    def _chain_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(self._empty_chain)
        layout.addWidget(self._table, 1)
        return content

    def _table_widget(self, columns: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setContextMenuPolicy(Qt.NoContextMenu)
        table.setWordWrap(True)
        table.horizontalHeader().setMinimumHeight(34)
        table.verticalHeader().setVisible(False)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return table

    def render(self, view: DashboardOptionChainView) -> None:
        if not isinstance(view, DashboardOptionChainView):
            raise TypeError("view must be DashboardOptionChainView")
        self._render_runtime_status(view)
        self._cards["Positioning Bias"].set_value(view.positioning_bias)
        self._cards["OI PCR"].set_value(formatters.ratio(view.oi_pcr), kind="neutral")
        self._cards["Change OI PCR"].set_value(formatters.ratio(view.change_oi_pcr), kind="neutral")
        self._cards["ATM Strike"].set_value(formatters.price(view.atm_strike), kind="neutral")
        self._cards["Available"].set_value(formatters.yes_no(view.available))
        self._cards["Symbol"].set_value(view.symbol, kind="neutral")
        self._cards["Exchange"].set_value(view.exchange, kind="neutral")
        self._cards["Expiry"].set_value(formatters.date_text(view.expiry_date), kind="neutral")
        self._cards["Timestamp"].set_value(formatters.timestamp(view.timestamp), kind="neutral")
        self._cards["Underlying"].set_value(formatters.price(view.underlying_price), kind="neutral")
        self._cards["Strike Count"].set_value(formatters.integer(view.strike_count), kind="neutral")
        self._cards["Call Pressure"].set_value(view.call_pressure, kind=_pressure_kind(view.call_pressure))
        self._cards["Put Pressure"].set_value(view.put_pressure, kind=_pressure_kind(view.put_pressure))
        self._cards["Support"].set_value(formatters.price(view.support_strike), kind="neutral")
        self._cards["Resistance"].set_value(formatters.price(view.resistance_strike), kind="neutral")
        self._cards["Max Pain"].set_value(formatters.price(view.max_pain_strike), kind="neutral")
        self._cards["Max Call OI"].set_value(_strike_metric(view.max_call_oi_strike, view.max_call_oi_value), kind="neutral")
        self._cards["Max Put OI"].set_value(_strike_metric(view.max_put_oi_strike, view.max_put_oi_value), kind="neutral")
        self._cards["Max Call Change OI"].set_value(_strike_metric(view.max_call_change_oi_strike, view.max_call_change_oi_value), kind="neutral")
        self._cards["Max Put Change OI"].set_value(_strike_metric(view.max_put_change_oi_strike, view.max_put_change_oi_value), kind="neutral")
        self._cards["Total Call OI"].set_value(formatters.integer(view.total_call_oi), kind="neutral")
        self._cards["Total Put OI"].set_value(formatters.integer(view.total_put_oi), kind="neutral")
        self._cards["Total Call Change OI"].set_value(formatters.integer(view.total_call_change_oi), kind="neutral")
        self._cards["Total Put Change OI"].set_value(formatters.integer(view.total_put_change_oi), kind="neutral")
        self._render_runtime_table(view)
        self._render_event_table(view)
        self._render_strikes(view)

    def _render_runtime_status(self, view: DashboardOptionChainView) -> None:
        status_kind = _runtime_kind(view.runtime_status)
        self._cards["Status"].set_value(view.runtime_status, kind=status_kind)
        self._cards["Runtime State"].set_value(view.runtime_status, kind=status_kind)
        enabled = view.runtime_status != "Disabled"
        self._cards["Enabled"].set_value(formatters.yes_no(enabled), kind="positive" if enabled else "neutral")
        self._cards["Configured"].set_value(formatters.yes_no(enabled), kind="neutral")
        self._cards["Started"].set_value(formatters.yes_no(view.runtime_status not in {"Disabled", "Starting"}), kind="neutral")
        self._cards["Last Underlying"].set_value(view.runtime_underlying, kind="neutral")
        self._cards["Nearest Expiry"].set_value(formatters.date_text(view.runtime_expiry), kind="neutral")
        self._cards["Contracts Active"].set_value(formatters.integer(view.runtime_subscribed_contracts), kind="neutral")
        self._cards["Contracts Total"].set_value(formatters.integer(view.runtime_subscribed_contracts), kind="neutral")
        self._cards["Last Update"].set_value(formatters.timestamp(view.runtime_last_update), kind="neutral")
        self._cards["Last Error"].set_value(view.runtime_last_error or formatters.MISSING, kind="negative" if view.runtime_last_error else "neutral")
        self._cards["Current Spot"].set_value(formatters.price(view.current_spot), kind="neutral")
        self._cards["Resolved ATM"].set_value(formatters.price(view.runtime_atm_strike), kind="neutral")
        self._cards["Contracts Resolved"].set_value(formatters.integer(view.contracts_resolved), kind="neutral")
        self._cards["Spot Ticks"].set_value("1" if view.last_spot_tick_at is not None else "0", kind="neutral")
        self._cards["Option Ticks"].set_value(formatters.integer(view.option_ticks_received), kind="neutral")
        self._cards["Last Spot Tick"].set_value(formatters.timestamp(view.last_spot_tick_at), kind="neutral")
        self._cards["Last Option Tick"].set_value(formatters.timestamp(view.last_option_tick_at), kind="neutral")
        self._cards["Analytics Updated"].set_value(formatters.yes_no(view.analytics_updated), kind="positive" if view.analytics_updated else "warning")
        self._cards["Message"].set_value(view.runtime_message, kind=status_kind)
        self._cards["Market Feed"].set_value(_health_text(view.health_market_feed), kind=_health_kind(view.health_market_feed))
        self._cards["Spot Feed"].set_value(_health_text(view.health_spot_feed), kind=_health_kind(view.health_spot_feed))
        self._cards["Discovery"].set_value(_health_text(view.health_discovery), kind=_health_kind(view.health_discovery))
        self._cards["Subscription"].set_value(_health_text(view.health_subscription), kind=_health_kind(view.health_subscription))
        self._cards["Option Feed"].set_value(_health_text(view.health_option_feed), kind=_health_kind(view.health_option_feed))
        self._cards["Analytics"].set_value(_health_text(view.health_analytics), kind=_health_kind(view.health_analytics))
        self._cards["Dashboard"].set_value(_health_text(view.health_dashboard), kind=_health_kind(view.health_dashboard))

    def _render_runtime_table(self, view: DashboardOptionChainView) -> None:
        rows = tuple(view.runtime_rows)
        self._runtime_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            values = (
                item.instrument,
                item.state,
                formatters.date_text(item.expiry),
                formatters.integer(item.contracts),
                formatters.integer(item.option_ticks),
                formatters.timestamp(item.last_update),
                item.last_error or formatters.MISSING,
            )
            for column, value in enumerate(values):
                self._runtime_table.setItem(row, column, _read_only_item(value))
        self._runtime_table.resizeColumnsToContents()
        self._runtime_table.resizeRowsToContents()

    def _render_event_table(self, view: DashboardOptionChainView) -> None:
        rows = tuple(view.event_rows)
        self._event_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            for column, value in enumerate((item.timestamp, item.instrument, item.state, item.message)):
                self._event_table.setItem(row, column, _read_only_item(value))
        self._event_table.resizeColumnsToContents()
        self._event_table.resizeRowsToContents()

    def _render_strikes(self, view: DashboardOptionChainView) -> None:
        rows = select_display_strikes(view)
        self._empty_chain.setText(formatters.MISSING if rows else _empty_chain_message(view))
        self._empty_chain.setVisible(not rows)
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
                item = _read_only_item(value)
                item.setData(Qt.UserRole, row_tags)
                if row_tags:
                    item.setBackground(_row_color(row_tags))
                if STRIKE_COLUMNS[column] in {"Call Change OI", "Put Change OI"}:
                    _style_change_item(item, value)
                self._table.setItem(row, column, item)
        self._table.resizeColumnsToContents()


def _scroll(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    return scroll


def _read_only_item(value) -> QTableWidgetItem:
    item = QTableWidgetItem(formatters.text(value))
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item


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
    normalized = value.strip().lower()
    if normalized == "-":
        return "neutral"
    key = "_".join(part for part in normalized.replace("-", "_").replace(" ", "_").split("_") if part)
    if key in {"put_writing", "call_unwinding"}:
        return "positive"
    if key in {"call_writing", "put_unwinding"}:
        return "negative"
    if key in {"balanced", "unknown", "-"}:
        return "neutral"
    return "warning"


def _runtime_kind(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "receiving":
        return "positive"
    if normalized in {
        "waiting for spot",
        "discovering",
        "subscribing",
        "waiting for option ticks",
        "analytics waiting",
        "stale",
        "starting",
    }:
        return "warning"
    if normalized == "error":
        return "negative"
    return "neutral"


def _health_text(value: bool) -> str:
    return "OK" if value else "Waiting"


def _health_kind(value: bool) -> str:
    return "positive" if value else "warning"


def _empty_chain_message(view: DashboardOptionChainView) -> str:
    if view.runtime_status == "Disabled":
        return "Option-chain runtime disabled"
    if view.runtime_status == "Waiting For Spot":
        return "Waiting for first spot tick"
    if view.runtime_status == "Discovering":
        return "Discovering contracts"
    if view.runtime_status == "Subscribing":
        return "Subscribing to option contracts"
    if view.runtime_status == "Waiting For Option Ticks":
        return "Waiting for first option tick"
    if view.runtime_status == "Analytics Waiting":
        return "Analytics waiting for sufficient option ticks"
    if view.runtime_status == "Stale":
        return "Last option tick is stale"
    if view.runtime_status == "Error":
        return f"Runtime error: {view.runtime_last_error or formatters.MISSING}"
    return "Strike rows unavailable"


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
