"""
====================================================
Vision Trading OS
Dashboard Controller
====================================================
"""

from engine.market_data_engine import MarketDataEngine
from engine.simulator import MarketSimulator
from engine.candle_engine import CandleEngine


class DashboardController:

    def __init__(self):

        # Live Market Data
        self.market_engine = MarketDataEngine()

        # Candle Builder
        self.candle_engine = CandleEngine()

        # Temporary Market Simulator
        self.simulator = MarketSimulator()

    def update(self):
        """
        Update all engines with the latest ticks.
        """

        ticks = self.simulator.next_tick()

        for tick in ticks:

            # Update live snapshot
            self.market_engine.update_snapshot(tick)

            # Update current candle
            self.candle_engine.update_tick(tick)

    def get_market_data(self):
        """
        Latest market prices.
        """
        return self.market_engine.snapshots

    def get_candle(self, symbol):
        """
        Current candle for a symbol.
        """
        return self.candle_engine.get_current(symbol)