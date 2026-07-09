"""
====================================================
Vision Trading OS
CPR Calculator
====================================================
"""

from core.models.daily_ohlc import DailyOHLC

from engines.cpr.levels import CPRLevels


class CPRCalculator:
    """
    Responsible only for calculating CPR levels.

    No caching.
    No logging.
    No events.
    """

    @staticmethod
    def calculate(
        daily_ohlc: DailyOHLC,
    ) -> CPRLevels:

        previous_high = daily_ohlc.high
        previous_low = daily_ohlc.low
        previous_close = daily_ohlc.close
        trading_date = daily_ohlc.trading_date

        if previous_high <= previous_low:
            raise ValueError(
                "Previous High must be greater than Previous Low."
            )

        # --------------------------------------------------
        # CPR Calculations
        # --------------------------------------------------

        pivot = (
            previous_high
            + previous_low
            + previous_close
        ) / 3

        bc = (
            previous_high
            + previous_low
        ) / 2

        tc = (pivot * 2) - bc

        # Ensure BC is always lower than TC
        if bc > tc:
            bc, tc = tc, bc

        width = tc - bc

        width_percentage = (
            (width / pivot) * 100
        )

        return CPRLevels(
            trading_date=trading_date,

            previous_high=previous_high,
            previous_low=previous_low,
            previous_close=previous_close,

            pivot=round(pivot, 2),

            bc=round(bc, 2),
            tc=round(tc, 2),

            width=round(width, 2),
            width_percentage=round(width_percentage, 4),
        )