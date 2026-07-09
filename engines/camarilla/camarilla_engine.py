"""
====================================================
Vision Trading OS
Camarilla Engine
====================================================
"""

from core.base_engine import BaseEngine
from core.events import CAMARILLA_UPDATED

from core.models.daily_ohlc import DailyOHLC

from engines.camarilla.calculator import CamarillaCalculator
from engines.camarilla.levels import CamarillaLevels


class CamarillaEngine(BaseEngine):
    """
    Camarilla Engine

    Responsibilities
    ----------------
    1. Calculate Camarilla Levels
    2. Cache today's levels
    3. Publish CAMARILLA_UPDATED event
    """

    def __init__(self, event_bus):

        super().__init__(event_bus)

    @property
    def levels(self) -> CamarillaLevels | None:
        """
        Returns today's Camarilla Levels.
        """
        return self._data

    def calculate(
        self,
        daily_ohlc: DailyOHLC,
    ) -> CamarillaLevels:

        # Prevent duplicate calculation
        if (
            self._data is not None
            and self._data.trading_date == daily_ohlc.trading_date
        ):
            return self._data

        self._data = CamarillaCalculator.calculate(
            daily_ohlc
        )

        self._event_bus.publish(
            CAMARILLA_UPDATED,
            self._data,
        )

        return self._data