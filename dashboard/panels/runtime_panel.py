"""
Runtime status dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QGroupBox, QHBoxLayout, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardRuntimeView
from dashboard.widgets import FieldGrid, MetricCard, StatusBadge


RUNTIME_COMPONENT_HEALTH_LABELS = (
    "Candle",
    "Market Data",
    "CPR",
    "Camarilla",
    "VWAP",
    "ADR",
    "Price Action",
    "Option Chain",
    "TradingView Evidence",
    "Fusion",
    "Market State",
    "Expert Setup",
    "Chart Explanation",
    "AI Reasoning",
    "Strategy",
    "Risk",
    "Lifecycle",
    "Journal",
    "Vision Daily Context",
    "Vision Method Calculator",
    "Vision Validation",
    "Vision Runtime Adapter",
    "TradeCandidate",
    "Vision Paper Handoff",
    "AI Explanation",
    "Broker Auth",
    "Broker Connection",
    "Broker Margins",
    "Broker Positions",
    "Broker Holdings",
    "Broker Orders",
    "Broker Account Sync",
    "Broker Mutation Mode",
)
RUNTIME_COMPONENT_HEALTH_FIELDS = tuple(f"Health: {label}" for label in RUNTIME_COMPONENT_HEALTH_LABELS)


class RuntimePanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Runtime", parent)
        self._labels = {}
        self._cards = {
            "Application": MetricCard("Application"),
            "Safety": MetricCard("Safety"),
            "Broker": MetricCard("Broker"),
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
        grid = FieldGrid(
            (
                "Instruments",
                "Market Data",
                "Journal",
                "Starts",
                "Stops",
                "Restarts",
                "Started At",
                "Stopped At",
                "Last Error",
                "Validation Mode",
                "Validation State",
                "Validation Health",
                "Validation Findings",
                "Validation Reconnects",
                "Validation P95 Latency",
                "Validation Broker Calls",
                "Replay State",
                "Replay Mode",
                "Replay Session",
                "Replay Source",
                "Replay Instruments",
                "Replay Trading Date",
                "Replay Sequence",
                "Replay Records",
                "Replay Progress",
                "Replay Speed",
                "Replay Timestamp",
                "Replay Outcome",
                "Replay Findings",
                "Replay Failure",
                "Broker Account",
                "Broker Account ID",
                "Broker Authentication",
                "Broker Connection",
                "Broker Last Refresh",
                "Broker Data Age",
                "Broker Available Margin",
                "Broker Used Margin",
                "Broker Positions",
                "Broker Holdings",
                "Broker Orders",
                "Broker Blocking Reason",
                "Broker Mutation Mode",
                *RUNTIME_COMPONENT_HEALTH_FIELDS,
            )
        )
        layout.addWidget(grid)
        self._labels.update(grid.labels)
        for field in ("Application", "Safety", "Broker"):
            self._labels[field] = self._cards[field].value_label
        self._labels["Market Data"] = StatusBadge()
        self._labels["Journal"] = StatusBadge()
        detail_grid = grid.layout()
        detail_grid.replaceWidget(grid.labels["Market Data"], self._labels["Market Data"])
        grid.labels["Market Data"].deleteLater()
        detail_grid.replaceWidget(grid.labels["Journal"], self._labels["Journal"])
        grid.labels["Journal"].deleteLater()
        for field in RUNTIME_COMPONENT_HEALTH_FIELDS:
            self._labels[field] = StatusBadge()
            detail_grid.replaceWidget(grid.labels[field], self._labels[field])
            grid.labels[field].deleteLater()

    def render(self, view: DashboardRuntimeView) -> None:
        self._cards["Application"].set_value(view.application_status)
        self._cards["Safety"].set_value(view.safety_mode)
        self._cards["Broker"].set_value(view.broker_mode)
        self._labels["Instruments"].setText(formatters.joined(view.configured_instruments))
        self._labels["Market Data"].set_status_text(formatters.ready(view.market_data_ready))
        self._labels["Journal"].set_status_text(formatters.ready(view.trade_journal_ready))
        self._labels["Starts"].setText(formatters.integer(view.start_count))
        self._labels["Stops"].setText(formatters.integer(view.stop_count))
        self._labels["Restarts"].setText(formatters.integer(view.restart_count))
        self._labels["Started At"].setText(formatters.timestamp(view.last_started_at))
        self._labels["Stopped At"].setText(formatters.timestamp(view.last_stopped_at))
        self._labels["Last Error"].setText(formatters.text(view.last_error))
        self._labels["Validation Mode"].setText(formatters.text(view.validation_mode))
        self._labels["Validation State"].setText(formatters.text(view.validation_state))
        self._labels["Validation Health"].setText(formatters.text(view.validation_health))
        self._labels["Validation Findings"].setText(formatters.integer(view.validation_findings))
        self._labels["Validation Reconnects"].setText(formatters.integer(view.validation_reconnects))
        self._labels["Validation P95 Latency"].setText(formatters.ratio(view.validation_p95_latency_ms))
        self._labels["Validation Broker Calls"].setText(formatters.integer(view.validation_broker_order_calls))
        self._labels["Replay State"].setText(formatters.text(view.replay_state))
        self._labels["Replay Mode"].setText(formatters.text(view.replay_mode))
        self._labels["Replay Session"].setText(formatters.text(view.replay_session_id))
        self._labels["Replay Source"].setText(formatters.text(view.replay_source))
        self._labels["Replay Instruments"].setText(formatters.joined(view.replay_instruments))
        self._labels["Replay Trading Date"].setText(formatters.date_text(view.replay_trading_date))
        self._labels["Replay Sequence"].setText(formatters.integer(view.replay_sequence))
        self._labels["Replay Records"].setText(f"{formatters.integer(view.replay_published_records)} / {formatters.integer(view.replay_total_records)}")
        self._labels["Replay Progress"].setText(formatters.ratio(view.replay_progress_percentage))
        self._labels["Replay Speed"].setText(formatters.ratio(view.replay_speed_multiplier))
        self._labels["Replay Timestamp"].setText(formatters.timestamp(view.replay_current_timestamp))
        self._labels["Replay Outcome"].setText(formatters.text(view.replay_outcome))
        self._labels["Replay Findings"].setText(formatters.integer(view.replay_findings))
        self._labels["Replay Failure"].setText(formatters.text(view.replay_failure_summary))
        self._labels["Broker Account"].setText(formatters.text(view.broker_account_broker))
        self._labels["Broker Account ID"].setText(formatters.text(view.broker_account_id))
        self._labels["Broker Authentication"].setText(formatters.text(view.broker_authentication))
        self._labels["Broker Connection"].setText(formatters.text(view.broker_connection))
        self._labels["Broker Last Refresh"].setText(formatters.timestamp(view.broker_last_refresh))
        self._labels["Broker Data Age"].setText(formatters.ratio(view.broker_data_age_seconds))
        self._labels["Broker Available Margin"].setText(formatters.price(view.broker_available_margin))
        self._labels["Broker Used Margin"].setText(formatters.price(view.broker_used_margin))
        self._labels["Broker Positions"].setText(formatters.integer(view.broker_open_positions))
        self._labels["Broker Holdings"].setText(formatters.integer(view.broker_holdings_count))
        self._labels["Broker Orders"].setText(formatters.integer(view.broker_orders_count))
        self._labels["Broker Blocking Reason"].setText(formatters.text(view.broker_blocking_reason))
        self._labels["Broker Mutation Mode"].setText(formatters.text(view.broker_mutation_mode))
        health = {item.name: item for item in view.component_health}
        for name, field in zip(RUNTIME_COMPONENT_HEALTH_LABELS, RUNTIME_COMPONENT_HEALTH_FIELDS):
            item = health.get(name)
            status = item.status if item is not None else "Waiting"
            self._labels[field].set_status_text(status)
            self._labels[field].setToolTip(item.detail if item is not None else "-")
