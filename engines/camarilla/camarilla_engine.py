"""
====================================================
Vision Trading OS
Camarilla Engine
====================================================
"""

from datetime import date

from core.event_bus import EventBus
from core.events import CAMARILLA_UPDATED

from engines.camarilla.calculator import CamarillaCalculator
from engines.camarilla.levels import CamarillaLevels


class CamarillaEngine:
    """
    Responsible for calculating and storing
    today's Camarilla levels.
    """

    def __init__(self, event_bus: EventBus):

        self._event_bus = event_bus
        self._levels: CamarillaLevels | None = None

    @property
    def levels(self) -> CamarillaLevels | None:
        return self._levels

    def calculate(
        self,
        trading_date: date,
        previous_high: float,
        previous_low: float,
        previous_close: float,
    ) -> CamarillaLevels:

        # Prevent duplicate calculation
        if (
            self._levels is not None
            and self._levels.trading_date == trading_date
        ):
            return self._levels

        self._levels = CamarillaCalculator.calculate(
            trading_date,
            previous_high,
            previous_low,
            previous_close,
        )

        # Publish event
        self._event_bus.publish(
            CAMARILLA_UPDATED,
            self._levels,
        )

        return self._levels

    def is_ready(self) -> bool:
        return self._levels is not None

    def clear(self):
        self._levels = None