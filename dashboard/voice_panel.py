from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class VoicePanel(QFrame):

    def __init__(self):
        super().__init__()

        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("🎤 Voice Assistant"))
        layout.addWidget(QLabel(""))

        layout.addWidget(QLabel("Status : Ready"))
        layout.addWidget(QLabel(""))
        layout.addWidget(QLabel("Last Command"))
        layout.addWidget(QLabel(""))
        layout.addWidget(QLabel("Last Response"))

        layout.addStretch()