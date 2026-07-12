"""
Runtime status dashboard panel.
"""

from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel

from dashboard.models import DashboardRuntimeView


class RuntimePanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Runtime", parent)
        self._labels = {}
        layout = QGridLayout(self)
        fields = (
            "Application",
            "Safety",
            "Broker",
            "Instruments",
            "Market Data",
            "Journal",
            "Starts",
            "Stops",
            "Restarts",
            "Started At",
            "Stopped At",
            "Last Error",
        )
        for row, field in enumerate(fields):
            layout.addWidget(QLabel(field), row, 0)
            label = QLabel("-")
            layout.addWidget(label, row, 1)
            self._labels[field] = label

    def render(self, view: DashboardRuntimeView) -> None:
        self._labels["Application"].setText(_text(view.application_status))
        self._labels["Safety"].setText(_text(view.safety_mode))
        self._labels["Broker"].setText(_text(view.broker_mode))
        self._labels["Instruments"].setText(", ".join(view.configured_instruments) or "-")
        self._labels["Market Data"].setText(_bool(view.market_data_ready))
        self._labels["Journal"].setText(_bool(view.trade_journal_ready))
        self._labels["Starts"].setText(str(view.start_count))
        self._labels["Stops"].setText(str(view.stop_count))
        self._labels["Restarts"].setText(str(view.restart_count))
        self._labels["Started At"].setText(_timestamp(view.last_started_at))
        self._labels["Stopped At"].setText(_timestamp(view.last_stopped_at))
        self._labels["Last Error"].setText(_text(view.last_error))


def _bool(value: bool) -> str:
    return "Ready" if value else "Not Ready"


def _text(value) -> str:
    return str(value) if value not in (None, "") else "-"


def _timestamp(value) -> str:
    return value.isoformat(sep=" ", timespec="seconds") if value is not None else "-"
