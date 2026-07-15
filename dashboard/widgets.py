"""
Reusable read-only dashboard widgets.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from dashboard import formatters


class StatusBadge(QLabel):
    def __init__(self, text: str = formatters.MISSING, parent=None):
        super().__init__(text, parent)
        self.setProperty("role", "status-badge")
        self.setProperty("status", "neutral")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(72)

    def set_status_text(self, value, *, kind: str | None = None) -> None:
        text = formatters.text(value)
        self.setText(text)
        self.setProperty("status", kind or formatters.semantic_kind(text))
        self.style().unpolish(self)
        self.style().polish(self)


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = formatters.MISSING, parent=None):
        super().__init__(parent)
        self.setProperty("role", "metric-card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        self._title = QLabel(title)
        self._title.setProperty("role", "metric-title")
        self._value = QLabel(value)
        self._value.setProperty("role", "metric-value")
        layout.addWidget(self._title)
        layout.addWidget(self._value)

    def set_value(self, value, *, kind: str | None = None) -> None:
        text = formatters.text(value)
        self._value.setText(text)
        self._value.setProperty("status", kind or formatters.semantic_kind(text))
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)

    @property
    def value_label(self) -> QLabel:
        return self._value


class FieldGrid(QWidget):
    def __init__(self, fields: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.labels: dict[str, QLabel] = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(8)
        for row, field in enumerate(fields):
            name = QLabel(field)
            name.setProperty("role", "field-name")
            value = QLabel(formatters.MISSING)
            value.setProperty("role", "field-value")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(name, row, 0)
            layout.addWidget(value, row, 1)
            self.labels[field] = value
