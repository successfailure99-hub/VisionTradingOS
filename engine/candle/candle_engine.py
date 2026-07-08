"""
====================================================
Vision Trading OS
Multi-Timeframe Candle Engine
====================================================
"""

from collections import defaultdict

from models.candle import Candle


class CandleEngine:

    def __init__(self):

        self.current = {}

        self.history = defaultdict(list)

    def update_tick(self, snapshot):

        symbol = snapshot.symbol

        price = snapshot.last_price

        if symbol not in self.current:

            candle = Candle(
                symbol=symbol,
                timeframe="5m",
                start_time=snapshot.timestamp,
                end_time=snapshot.timestamp,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=snapshot.volume,
            )

            self.current[symbol] = candle

            return

        candle = self.current[symbol]

        candle.high = max(candle.high, price)

        candle.low = min(candle.low, price)

        candle.close = price

        candle.volume += snapshot.volume

        candle.end_time = snapshot.timestamp

    def get_current(self, symbol):

        return self.current.get(symbol)

    def get_history(self, symbol):

        return self.history[symbol]