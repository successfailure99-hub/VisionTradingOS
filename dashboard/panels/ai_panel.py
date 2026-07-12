"""
AI reasoning dashboard panel.
"""

from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel

from dashboard.models import DashboardAIView


class AIPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("AI Reasoning", parent)
        self._labels = {}
        layout = QGridLayout(self)
        for row, field in enumerate(("Summary", "Confidence", "Agreement", "Conflict", "Suitability", "Missing", "Explanation")):
            layout.addWidget(QLabel(field), row, 0)
            label = QLabel("-")
            label.setWordWrap(True)
            layout.addWidget(label, row, 1)
            self._labels[field] = label

    def render(self, view: DashboardAIView) -> None:
        self._labels["Summary"].setText(_text(view.market_summary))
        self._labels["Confidence"].setText(_text(view.confidence))
        self._labels["Agreement"].setText(_text(view.agreement))
        self._labels["Conflict"].setText(_text(view.conflict))
        self._labels["Suitability"].setText(_text(view.trading_suitability))
        self._labels["Missing"].setText(", ".join(view.missing_information) or "-")
        self._labels["Explanation"].setText(_text(view.explanation))


def _text(value) -> str:
    return str(value) if value not in (None, "") else "-"
