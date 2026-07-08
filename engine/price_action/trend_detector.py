"""
====================================================
Trend Detector
====================================================
"""


class TrendDetector:

    def detect(self, candles):

        if len(candles) < 3:

            return "UNKNOWN"

        c1 = candles[-3]
        c2 = candles[-2]
        c3 = candles[-1]

        if c1.close < c2.close < c3.close:

            return "BULLISH"

        if c1.close > c2.close > c3.close:

            return "BEARISH"

        return "RANGE"