"""
Reusable read-only dashboard widgets.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from dashboard import formatters


def configure_readable_label(label: QLabel) -> QLabel:
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
    return label


def set_label_text(label: QLabel, value) -> bool:
    text = formatters.text(value)
    if label.text() == text:
        return False
    label.setText(text)
    return True


class StatusBadge(QLabel):
    def __init__(self, text: str = formatters.MISSING, parent=None):
        super().__init__(text, parent)
        self.setProperty("role", "status-badge")
        self.setProperty("status", "neutral")
        self._status_text = formatters.text(text)
        self._status_kind = "neutral"
        self._repolish_count = 0
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(72)
        self.setMinimumHeight(28)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

    def set_status_text(self, value, *, kind: str | None = None) -> bool:
        text = formatters.text(value)
        status_kind = kind or formatters.semantic_kind(text)
        if text == self._status_text and status_kind == self._status_kind:
            return False
        if text != self._status_text:
            self.setText(text)
            self._status_text = text
        if status_kind != self._status_kind:
            self.setProperty("status", status_kind)
            self._status_kind = status_kind
            self.style().unpolish(self)
            self.style().polish(self)
            self._repolish_count += 1
        return True

    @property
    def repolish_count(self) -> int:
        return self._repolish_count


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = formatters.MISSING, parent=None):
        super().__init__(parent)
        self.setProperty("role", "metric-card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        self._title = QLabel(title)
        self._title.setProperty("role", "metric-title")
        self._title.setMinimumHeight(18)
        configure_readable_label(self._title)
        self._value = QLabel(value)
        self._value.setProperty("role", "metric-value")
        self._value.setProperty("status", "neutral")
        self._value_text = formatters.text(value)
        self._value_kind = "neutral"
        self._repolish_count = 0
        self._value.setMinimumHeight(26)
        configure_readable_label(self._value)
        layout.addWidget(self._title)
        layout.addWidget(self._value)
        self.setMinimumHeight(76)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, value, *, kind: str | None = None) -> bool:
        text = formatters.text(value)
        status_kind = kind or formatters.semantic_kind(text)
        if text == self._value_text and status_kind == self._value_kind:
            return False
        if text != self._value_text:
            self._value.setText(text)
            self._value_text = text
        if status_kind != self._value_kind:
            self._value.setProperty("status", status_kind)
            self._value_kind = status_kind
            self._value.style().unpolish(self._value)
            self._value.style().polish(self._value)
            self._repolish_count += 1
        return True

    @property
    def value_label(self) -> QLabel:
        return self._value

    @property
    def repolish_count(self) -> int:
        return self._repolish_count


class FieldGrid(QWidget):
    def __init__(self, fields: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.labels: dict[str, QLabel] = {}
        self.name_labels: dict[str, QLabel] = {}
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(10)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        for row, field in enumerate(fields):
            name = QLabel(field)
            name.setProperty("role", "field-name")
            name.setMinimumHeight(24)
            name.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            value = QLabel(formatters.MISSING)
            value.setProperty("role", "field-value")
            value.setMinimumHeight(24)
            value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            configure_readable_label(value)
            layout.addWidget(name, row, 0)
            layout.addWidget(value, row, 1)
            layout.setRowMinimumHeight(row, 28)
            self.labels[field] = value
            self.name_labels[field] = name

    def set_value(self, field: str, value) -> bool:
        label = self.labels[field]
        text = formatters.text(value)
        if label.text() == text:
            return False
        label.setText(text)
        return True
