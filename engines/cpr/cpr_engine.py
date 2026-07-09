"""
====================================================
Vision Trading OS
CPR Engine
====================================================
"""

from core.base_engine import BaseEngine
from core.events import CPR_UPDATED

from core.models.daily_ohlc import DailyOHLC

from engines.cpr.calculator import CPRCalculator
from engines.cpr.levels import CPRLevels


class CPREngine(BaseEngine):
    """
    CPR Engine

    Responsibilities
    ----------------
    1. Calculate CPR Levels
    2. Cache today's CPR Levels
    3. Publish CPR_UPDATED event
    """

    def __init__(self, event_bus):

        super().__init__(event_bus)

    @property
    def levels(self) -> CPRLevels | None:
        """
        Returns today's CPR Levels.
        """
        return self._data

    def calculate(
        self,
        daily_ohlc: DailyOHLC,
    ) -> CPRLevels:

        # Prevent duplicate calculation
        if (
            self._data is not None
            and self._data.trading_date == daily_ohlc.trading_date
        ):
            return self._data

        self._data = CPRCalculator.calculate(
            daily_ohlc
        )

        self._event_bus.publish(
            CPR_UPDATED,
            self._data,
        )

        return self._data