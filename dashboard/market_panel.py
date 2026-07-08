"""
=====================================================
Vision Trading OS
Market Panel
=====================================================
"""

from PySide6.QtWidgets import QFrame
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QVBoxLayout

from PySide6.QtCore import Qt


class MarketPanel(QFrame):

    def __init__(self):

        super().__init__()

        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)

        title = QLabel("📈 MARKET WATCH")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title.setStyleSheet("""
            font-size:18px;
            font-weight:bold;
        """)

        layout.addWidget(title)

        layout.addSpacing(20)

        self.nifty = QLabel("NIFTY : ----")
        self.banknifty = QLabel("BANKNIFTY : ----")
        self.sensex = QLabel("SENSEX : ----")

        for label in [self.nifty, self.banknifty, self.sensex]:

            label.setStyleSheet("""
                font-size:18px;
                padding:8px;
            """)

            layout.addWidget(label)

        layout.addStretch()

    def update_market(self, snapshots):

        self.nifty.setText(
            f"NIFTY : {snapshots['NIFTY'].last_price:.2f}"
        )

        self.banknifty.setText(
            f"BANKNIFTY : {snapshots['BANKNIFTY'].last_price:.2f}"
        )

        self.sensex.setText(
            f"SENSEX : {snapshots['SENSEX'].last_price:.2f}"
        )