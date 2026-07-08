from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class AIPanel(QFrame):

    def __init__(self):
        super().__init__()

        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("🧠 AI Insights"))
        layout.addWidget(QLabel(""))

        layout.addWidget(QLabel("Trend"))
        layout.addWidget(QLabel("CPR"))
        layout.addWidget(QLabel("VWAP"))
        layout.addWidget(QLabel("Camarilla"))
        layout.addWidget(QLabel("Confidence"))

        layout.addStretch()