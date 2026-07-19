"""
Read-only deterministic backtest dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QPushButton, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardBacktestView
from dashboard.widgets import FieldGrid, MetricCard, StatusBadge


class BacktestPanel(QGroupBox):
    def __init__(self, command_target=None, parent=None):
        super().__init__("Backtest", parent)
        self._command_target = command_target
        self._labels = {}
        self._cards = {
            "State": MetricCard("State"),
            "Closed Trades": MetricCard("Closed Trades"),
            "Net P&L": MetricCard("Net P&L"),
            "Win Rate": MetricCard("Win Rate"),
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
                "Enabled",
                "Mode",
                "Current Session",
                "Sessions",
                "Replay Progress",
                "Drawdown",
                "Reproducibility",
                "Last Finding",
                "Outcome",
                "Report",
            )
        )
        layout.addWidget(grid)
        self._labels.update(grid.labels)
        self._labels["Enabled"] = StatusBadge()
        detail_grid = grid.layout()
        detail_grid.replaceWidget(grid.labels["Enabled"], self._labels["Enabled"])
        grid.labels["Enabled"].deleteLater()
        layout.addLayout(self._controls())

    def render(self, view: DashboardBacktestView) -> None:
        self._cards["State"].set_value(view.lifecycle_state)
        self._cards["Closed Trades"].set_value(formatters.integer(view.closed_trades))
        self._cards["Net P&L"].set_value(formatters.price(view.net_pnl), kind=formatters.pnl_kind(view.net_pnl))
        self._cards["Win Rate"].set_value(formatters.ratio(view.win_rate))
        self._labels["Enabled"].set_status_text(formatters.yes_no(view.enabled))
        self._labels["Mode"].setText(formatters.text(view.mode))
        self._labels["Current Session"].setText(formatters.text(view.current_session))
        self._labels["Sessions"].setText(f"{formatters.integer(view.completed_sessions)} / {formatters.integer(view.total_sessions)}")
        self._labels["Replay Progress"].setText(formatters.ratio(view.current_replay_progress))
        self._labels["Drawdown"].setText(formatters.price(view.drawdown))
        self._labels["Reproducibility"].setText(formatters.text(view.reproducibility_status))
        self._labels["Last Finding"].setText(formatters.text(view.last_finding))
        self._labels["Outcome"].setText(formatters.text(view.final_outcome))
        self._labels["Report"].setText(formatters.text(view.report_path))

    def _controls(self):
        layout = QHBoxLayout()
        for label, method in (
            ("Prepare", "prepare_backtest"),
            ("Start", "start_backtest"),
            ("Pause", "pause_backtest"),
            ("Resume", "resume_backtest"),
            ("Stop", "stop_backtest"),
            ("Reset", "reset_backtest"),
        ):
            button = QPushButton(label)
            connector = getattr(button.clicked, "connect")
            connector(lambda _checked=False, name=method: self._invoke(name))
            layout.addWidget(button)
        return layout

    def _invoke(self, method: str) -> None:
        target = self._command_target
        if target is None:
            return
        command = getattr(target, method, None)
        if callable(command):
            command()
