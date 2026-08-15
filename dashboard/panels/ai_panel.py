"""
AI reasoning dashboard panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout

from dashboard import formatters
from dashboard.models import DashboardAIView
from dashboard.widgets import FieldGrid, StatusBadge, set_label_text


class AIPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("AI Reasoning", parent)
        self._labels = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)
        grid = FieldGrid((
            "Summary", "Confidence", "Agreement", "Conflict", "Suitability",
            "Snapshot Generation", "Snapshot Created At", "Runtime Market Timestamp",
            "Vision Decision Timestamp", "Missing", "Explanation",
        ))
        layout.addWidget(grid)
        self._labels.update(grid.labels)
        for field in ("Confidence", "Agreement", "Suitability"):
            badge = StatusBadge()
            grid.layout().replaceWidget(grid.labels[field], badge)
            grid.labels[field].deleteLater()
            self._labels[field] = badge
        for field in ("Summary", "Conflict", "Missing", "Explanation"):
            self._labels[field].setWordWrap(True)

    def render(self, view: DashboardAIView) -> None:
        set_label_text(self._labels["Summary"], view.market_summary)
        self._labels["Confidence"].set_status_text(view.confidence)
        self._labels["Agreement"].set_status_text(view.agreement)
        set_label_text(self._labels["Conflict"], view.conflict)
        self._labels["Suitability"].set_status_text(view.trading_suitability)
        set_label_text(self._labels["Snapshot Generation"], view.snapshot_generation_id)
        set_label_text(self._labels["Snapshot Created At"], formatters.timestamp(view.snapshot_created_at))
        set_label_text(self._labels["Runtime Market Timestamp"], formatters.timestamp(view.runtime_market_timestamp))
        set_label_text(self._labels["Vision Decision Timestamp"], formatters.timestamp(view.vision_decision_timestamp))
        set_label_text(self._labels["Missing"], formatters.joined(view.missing_information))
        set_label_text(self._labels["Explanation"], view.explanation)
