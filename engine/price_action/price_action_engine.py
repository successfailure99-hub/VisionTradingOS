"""
====================================================
Price Action Engine
====================================================
"""

from engine.price_action.trend_detector import TrendDetector
from engine.price_action.structure_detector import StructureDetector

from models.engine_result import EngineResult


class PriceActionEngine:

    def __init__(self):

        self.trend = TrendDetector()

        self.structure = StructureDetector()

    def analyze(self, candles):

        result = EngineResult(engine="Price Action")

        result.trend = self.trend.detect(candles)

        result.evidence = self.structure.analyze(candles)

        score = len(result.evidence)

        result.confidence = min(score * 20, 100)

        if result.trend == "BULLISH":

            result.recommendation = "Bullish market"

        elif result.trend == "BEARISH":

            result.recommendation = "Bearish market"

        else:

            result.recommendation = "Wait"

        return result