from engines.camarilla.levels import CamarillaLevels
from datetime import date


class CamarillaCalculator:

    @staticmethod
    def calculate(
        trading_date: date,
        previous_high: float,
        previous_low: float,
        previous_close: float,
    ) -> CamarillaLevels:

        if previous_high <= previous_low:
            raise ValueError("Previous High must be greater than Previous Low.")

        rng = previous_high - previous_low

        h3 = previous_close + (rng * 1.1 / 4)
        h4 = previous_close + (rng * 1.1 / 2)

        l3 = previous_close - (rng * 1.1 / 4)
        l4 = previous_close - (rng * 1.1 / 2)

        # Extension levels
        h5 = (previous_high / previous_low) * previous_close
        l5 = previous_close - (h5 - previous_close)

        h6 = h5 + (h5 - h4)
        l6 = l5 - (l4 - l5)

        pivot = (
            previous_high +
            previous_low +
            previous_close
        ) / 3

        return CamarillaLevels(
            trading_date=trading_date,

            previous_high=previous_high,
            previous_low=previous_low,
            previous_close=previous_close,

            pivot=round(pivot, 2),

            h3=round(h3, 2),
            h4=round(h4, 2),
            h5=round(h5, 2),
            h6=round(h6, 2),

            l3=round(l3, 2),
            l4=round(l4, 2),
            l5=round(l5, 2),
            l6=round(l6, 2),
        )