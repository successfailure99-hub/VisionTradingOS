"""
Vision Trading OS
Market Simulator
"""

import random
import time

from models.market_snapshot import MarketSnapshot


class MarketSimulator:

    def __init__(self):

        self.nifty = 24500

        self.banknifty = 56000

        self.sensex = 80500

    def next_tick(self):

        self.nifty += random.uniform(-8, 8)

        self.banknifty += random.uniform(-25, 25)

        self.sensex += random.uniform(-40, 40)

        return [

            MarketSnapshot(
                symbol="NIFTY",
                last_price=round(self.nifty, 2)
            ),

            MarketSnapshot(
                symbol="BANKNIFTY",
                last_price=round(self.banknifty, 2)
            ),

            MarketSnapshot(
                symbol="SENSEX",
                last_price=round(self.sensex, 2)
            )

        ]