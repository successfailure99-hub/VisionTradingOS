"""
======================================================
Vision Trading OS
Market Data Engine
Version : 1.0
======================================================
"""

from datetime import datetime
from models.market_snapshot import MarketSnapshot


class MarketDataEngine:

    def __init__(self):

        self.connected = False

        self.snapshots = {
            "NIFTY": MarketSnapshot(symbol="NIFTY"),
            "BANKNIFTY": MarketSnapshot(symbol="BANKNIFTY"),
            "SENSEX": MarketSnapshot(symbol="SENSEX"),
        }

    def connect(self):

        self.connected = True

    def disconnect(self):

        self.connected = False

    def update_snapshot(self, snapshot: MarketSnapshot):

        self.snapshots[snapshot.symbol] = snapshot

    def get_snapshot(self, symbol):

        return self.snapshots.get(symbol)

    def server_time(self):

        return datetime.now().strftime("%H:%M:%S")