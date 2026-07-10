"""
====================================================
Vision Trading OS
Camarilla Engine
====================================================
"""

from datetime import date, datetime
from math import isfinite
from numbers import Real

from core.base_engine import BaseEngine
from core.events import CAMARILLA_UPDATED

from core.models.daily_ohlc import DailyOHLC

from engines.camarilla.calculator import CamarillaCalculator
from engines.camarilla.levels import CamarillaLevels


class CamarillaEngine(BaseEngine):
    """
    Deterministic daily Camarilla levels engine.

    Camarilla Engine V1 accepts one canonical DailyOHLC input at a
    time, validates it, calculates levels through CamarillaCalculator,
    caches only the latest accepted input and immutable result, and
    publishes CAMARILLA_UPDATED for newly accepted calculations.

    One CamarillaEngine instance represents one externally managed
    instrument context. Multi-instrument routing belongs upstream.

    Camarilla Engine V1 assumes serialized, single-threaded
    calculate/update calls. Thread safety and orchestration belong
    upstream. Historical storage, multi-timeframe behavior, strategy
    interpretation, and trading signals are outside V1.
    """

    def __init__(self, event_bus):

        super().__init__(event_bus)

        self._daily_ohlc: DailyOHLC | None = None
        self._levels: CamarillaLevels | None = None

    @property
    def daily_ohlc(self) -> DailyOHLC | None:
        """
        Return the latest accepted DailyOHLC input.
        """

        return self._daily_ohlc

    @property
    def levels(self) -> CamarillaLevels | None:
        """
        Return the latest immutable CamarillaLevels result.
        """

        return self._levels

    def calculate(
        self,
        daily_ohlc: DailyOHLC,
    ) -> CamarillaLevels:

        self._validate_daily_ohlc(daily_ohlc)

        if self._daily_ohlc is not None:
            if daily_ohlc.trading_date < self._daily_ohlc.trading_date:
                raise ValueError(
                    "Stale Camarilla DailyOHLC received: "
                    f"{daily_ohlc.trading_date.isoformat()} < "
                    f"{self._daily_ohlc.trading_date.isoformat()}"
                )

            if daily_ohlc == self._daily_ohlc:
                return self._levels

        levels = CamarillaCalculator.calculate(
            daily_ohlc
        )

        self._daily_ohlc = daily_ohlc
        self._levels = levels
        self._data = levels

        self._event_bus.publish(
            CAMARILLA_UPDATED,
            levels,
        )

        return levels

    def update(
        self,
        daily_ohlc: DailyOHLC,
    ) -> CamarillaLevels:
        """
        Backward-compatible alias for Camarilla calculation.
        """

        return self.calculate(daily_ohlc)

    def reset(self) -> None:
        """
        Clear accepted input, latest levels, and readiness.
        """

        super().clear()

        self._daily_ohlc = None
        self._levels = None

    def clear(self) -> None:
        """
        Clear all Camarilla state and reset readiness.
        """

        self.reset()

    def _validate_daily_ohlc(self, daily_ohlc: DailyOHLC) -> None:
        if not isinstance(daily_ohlc, DailyOHLC):
            raise TypeError("CamarillaEngine expects a DailyOHLC object.")

        if (
            not isinstance(daily_ohlc.trading_date, date)
            or isinstance(daily_ohlc.trading_date, datetime)
        ):
            raise ValueError("DailyOHLC trading_date must be a date.")

        self._validate_ohlc_value("open", daily_ohlc.open)
        self._validate_ohlc_value("high", daily_ohlc.high)
        self._validate_ohlc_value("low", daily_ohlc.low)
        self._validate_ohlc_value("close", daily_ohlc.close)

        if daily_ohlc.high <= daily_ohlc.low:
            raise ValueError("DailyOHLC high must be greater than low.")

        if not daily_ohlc.low <= daily_ohlc.open <= daily_ohlc.high:
            raise ValueError("DailyOHLC open must be within low and high.")

        if not daily_ohlc.low <= daily_ohlc.close <= daily_ohlc.high:
            raise ValueError("DailyOHLC close must be within low and high.")

    def _validate_ohlc_value(
        self,
        name: str,
        value: Real,
    ) -> None:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(
                f"DailyOHLC {name} must be a finite real number."
            )

        if not isfinite(value):
            raise ValueError(
                f"DailyOHLC {name} must be a finite real number."
            )

        if value <= 0:
            raise ValueError(
                f"DailyOHLC {name} must be greater than zero."
            )
