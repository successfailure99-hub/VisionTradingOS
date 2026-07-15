"""
AI reasoning dashboard panel.
"""

from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardAIView
from dashboard.widgets import FieldGrid, StatusBadge


class AIPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("AI Reasoning", parent)
        self._labels = {}
        layout = QVBoxLayout(self)
        grid = FieldGrid(("Summary", "Confidence", "Agreement", "Conflict", "Suitability", "Missing", "Explanation"))
        layout.addWidget(grid)
        self._labels.update(grid.labels)
        for field in ("Confidence", "Agreement", "Conflict", "Suitability"):
            badge = StatusBadge()
            grid.layout().replaceWidget(grid.labels[field], badge)
            grid.labels[field].deleteLater()
            self._labels[field] = badge
        for field in ("Summary", "Missing", "Explanation"):
            self._labels[field].setWordWrap(True)

    def render(self, view: DashboardAIView) -> None:
        self._labels["Summary"].setText(formatters.text(view.market_summary))
        self._labels["Confidence"].set_status_text(view.confidence)
        self._labels["Agreement"].set_status_text(view.agreement)
        self._labels["Conflict"].set_status_text(view.conflict)
        self._labels["Suitability"].set_status_text(view.trading_suitability)
        self._labels["Missing"].setText(formatters.joined(view.missing_information))
        self._labels["Explanation"].setText(formatters.text(view.explanation))
