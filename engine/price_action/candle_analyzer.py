"""
====================================================
Vision Trading OS
Candle Analyzer
====================================================
"""


class CandleAnalyzer:

    def analyze(self, candle):

        result = {}

        body = abs(candle.close - candle.open)

        total = candle.high - candle.low

        upper_wick = candle.high - max(candle.open, candle.close)

        lower_wick = min(candle.open, candle.close) - candle.low

        result["bullish"] = candle.close > candle.open

        result["bearish"] = candle.close < candle.open

        result["body"] = body

        result["range"] = total

        result["upper_wick"] = upper_wick

        result["lower_wick"] = lower_wick

        if total > 0:
            result["body_ratio"] = body / total
        else:
            result["body_ratio"] = 0

        result["strong_bullish"] = (
            result["bullish"]
            and result["body_ratio"] > 0.7
        )

        result["strong_bearish"] = (
            result["bearish"]
            and result["body_ratio"] > 0.7
        )

        result["doji"] = (
            result["body_ratio"] < 0.1
        )

        return result