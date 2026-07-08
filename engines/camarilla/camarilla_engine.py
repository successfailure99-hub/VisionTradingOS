"""
====================================================
Vision Trading OS
Camarilla Engine
====================================================
"""

from core.event_bus import EventBus
from core.events import CAMARILLA_UPDATED

from core.models.daily_ohlc import DailyOHLC

from engines.camarilla.calculator import CamarillaCalculator
from engines.camarilla.levels import CamarillaLevels


class CamarillaEngine:
    """
    Camarilla Engine

    Responsibilities
    ----------------
    1. Calculate today's Camarilla levels.
    2. Cache today's levels.
    3. Publish CAMARILLA_UPDATED event.
    """

    def __init__(self, event_bus: EventBus):

        self._event_bus = event_bus
        self._levels: CamarillaLevels | None = None

    @property
    def levels(self) -> CamarillaLevels | None:
        """
        Returns the latest calculated Camarilla Levels.
        """
        return self._levels

    def calculate(
        self,
        daily_ohlc: DailyOHLC,
    ) -> CamarillaLevels:
        """
        Calculate Camarilla levels using the previous day's OHLC.
        """

        # Prevent duplicate calculation for same trading day
        if (
            self._levels is not None
            and self._levels.trading_date == daily_ohlc.trading_date
        ):
            return self._levels

        self._levels = CamarillaCalculator.calculate(
            daily_ohlc
        )

        # Publish event
        self._event_bus.publish(
            CAMARILLA_UPDATED,
            self._levels,
        )

        return self._levels

    def is_ready(self) -> bool:
        """
        Returns True if today's Camarilla levels
        have already been calculated.
        """
        return self._levels is not None

    def clear(self) -> None:
        """
        Clears today's cached Camarilla levels.
        """
        self._levels = None