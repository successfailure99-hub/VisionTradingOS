from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QFrame,
)

from engine.simulator import MarketSimulator
from dashboard.market_panel import MarketPanel
from dashboard.ai_panel import AIPanel
from dashboard.voice_panel import VoicePanel


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Vision Trading OS")
        self.resize(1500, 850)

        # Simulator
        self.simulator = MarketSimulator()

        # Build UI
        self.build_ui()

        # Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_market)
        self.timer.start(1000)

    def build_ui(self):

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)

        # Header
        title = QLabel("Vision Trading OS")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""
            font-size:30px;
            font-weight:bold;
            color:#00d084;
            padding:10px;
        """)

        main_layout.addWidget(title)

        # Three Panels
        panels = QHBoxLayout()

        self.market_panel = MarketPanel()

        panels.addWidget(self.market_panel, 1)
        panels.addWidget(AIPanel(), 2)
        panels.addWidget(VoicePanel(), 1)

        main_layout.addLayout(panels)

        # Status Bar
        status = QFrame()
        status.setFrameShape(QFrame.Shape.StyledPanel)

        status_layout = QHBoxLayout(status)

        self.status_label = QLabel("Status : Waiting for market data...")
        status_layout.addWidget(self.status_label)

        main_layout.addWidget(status)

    def update_market(self):
        """Update simulated market data every second."""

        ticks = self.simulator.next_tick()

        snapshots = {}

        for tick in ticks:
            snapshots[tick.symbol] = tick

        self.market_panel.update_market(snapshots)