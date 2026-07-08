"""
====================================================
Structure Detector
====================================================
"""


class StructureDetector:

    def analyze(self, candles):

        if len(candles) < 2:

            return []

        previous = candles[-2]

        current = candles[-1]

        evidence = []

        if current.high > previous.high:

            evidence.append("Higher High")

        if current.low > previous.low:

            evidence.append("Higher Low")

        if current.high < previous.high:

            evidence.append("Lower High")

        if current.low < previous.low:

            evidence.append("Lower Low")

        return evidence