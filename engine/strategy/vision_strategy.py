"""
====================================================
Vision Intraday Strategy V1
====================================================
"""

from models.strategy_result import StrategyResult


class VisionStrategy:

    def evaluate(
        self,
        price_action,
        market_context,
        confirmation,
        option_chain=None,
    ):

        result = StrategyResult(strategy="Vision Intraday")

        # ---------- Mandatory Conditions ----------

        if price_action.trend != "BULLISH":
            result.risks.append("Trend not bullish")
            return result

        if "Higher High" not in price_action.evidence:
            result.risks.append("No Higher High")
            return result

        if "Higher Low" not in price_action.evidence:
            result.risks.append("No Higher Low")
            return result

        # ---------- Confirmation ----------

        if getattr(confirmation, "above_vwap", False):
            result.reasons.append("Above VWAP")

        if getattr(confirmation, "above_h3", False):
            result.reasons.append("Above H3")

        if getattr(confirmation, "narrow_cpr", False):
            result.reasons.append("Narrow CPR")

        # ---------- Option Chain (optional for V1) ----------

        if option_chain is not None:
            if getattr(option_chain, "fresh_put_writing", False):
                result.reasons.append("Fresh Put Writing")

        result.signal = "POTENTIAL_LONG"

        result.confidence = 70 + len(result.reasons) * 5

        result.recommendation = (
            "Wait for a confirmed 5-minute candle close before entry."
        )

        return result