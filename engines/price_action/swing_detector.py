"""
Stateless confirmed swing detection for Price Action Engine V1.
"""

from core.models.candle import Candle
from engines.price_action.enums import SwingType
from engines.price_action.models import SwingPoint


class SwingDetector:
    """
    Detects the single newly confirmable swing candidate.

    Confirmation is delayed by right-side bars and uses strict
    inequality against the left and right windows. If one outside
    candle qualifies as both a swing high and swing low, V1 returns no
    swing for that candidate to avoid ambiguous sequence ordering.
    """

    @staticmethod
    def detect_confirmed_swing(
        candles: tuple[Candle, ...],
        left_bars: int,
        right_bars: int,
    ) -> SwingPoint | None:
        candidate_index = len(candles) - right_bars - 1

        if candidate_index < left_bars:
            return None

        if candidate_index + right_bars >= len(candles):
            return None

        candidate = candles[candidate_index]
        left_window = candles[candidate_index - left_bars:candidate_index]
        right_window = candles[candidate_index + 1:candidate_index + right_bars + 1]

        is_high = all(candidate.high > candle.high for candle in left_window)
        is_high = is_high and all(candidate.high > candle.high for candle in right_window)

        is_low = all(candidate.low < candle.low for candle in left_window)
        is_low = is_low and all(candidate.low < candle.low for candle in right_window)

        if is_high == is_low:
            return None

        if is_high:
            return SwingPoint(
                symbol=str(candidate.symbol).strip().upper(),
                timeframe=str(candidate.timeframe).strip(),
                swing_type=SwingType.HIGH,
                structure_type=None,
                price=candidate.high,
                candle_start_time=candidate.start_time,
                candle_end_time=candidate.end_time,
                candle_index=candidate_index,
            )

        return SwingPoint(
            symbol=str(candidate.symbol).strip().upper(),
            timeframe=str(candidate.timeframe).strip(),
            swing_type=SwingType.LOW,
            structure_type=None,
            price=candidate.low,
            candle_start_time=candidate.start_time,
            candle_end_time=candidate.end_time,
            candle_index=candidate_index,
        )