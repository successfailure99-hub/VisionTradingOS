"""
====================================================
Vision Trading OS
CPR Engine
====================================================
"""

from datetime import date, datetime
from math import isfinite
from numbers import Real

from core.base_engine import BaseEngine
from core.events import CPR_UPDATED

from core.models.daily_ohlc import DailyOHLC

from engines.cpr.calculator import CPRCalculator
from engines.cpr.levels import CPRLevels


class CPREngine(BaseEngine):
    """
    Deterministic daily Central Pivot Range engine.

    CPR Engine V1 accepts one canonical DailyOHLC input at a time,
    validates it, calculates CPR levels through CPRCalculator, caches
    only the latest accepted input and immutable CPRLevels result, and
    publishes CPR_UPDATED for newly accepted calculations.

    One CPREngine instance represents one externally managed instrument
    context. Multi-instrument orchestration belongs upstream.

    CPR Engine V1 assumes serialized, single-threaded calculate/update
    calls. Thread safety and orchestration belong upstream; internal
    locking and asynchronous processing are outside V1. Multi-timeframe
    and historical CPR behavior belong to future versions.
    """

    def __init__(self, event_bus):

        super().__init__(event_bus)

        self._daily_ohlc: DailyOHLC | None = None
        self._levels: CPRLevels | None = None

    @property
    def levels(self) -> CPRLevels | None:
        """
        Return the latest immutable CPRLevels result.
        """

        return self._levels

    @property
    def daily_ohlc(self) -> DailyOHLC | None:
        """
        Return the latest accepted DailyOHLC input.
        """

        return self._daily_ohlc

    def calculate(
        self,
        daily_ohlc: DailyOHLC,
    ) -> CPRLevels:

        self._validate_daily_ohlc(daily_ohlc)

        if self._daily_ohlc is not None:
            if daily_ohlc.trading_date < self._daily_ohlc.trading_date:
                raise ValueError(
                    "Stale CPR DailyOHLC received: "
                    f"{daily_ohlc.trading_date.isoformat()} < "
                    f"{self._daily_ohlc.trading_date.isoformat()}"
                )

            if daily_ohlc == self._daily_ohlc:
                return self._levels

        levels = CPRCalculator.calculate(
            daily_ohlc
        )

        self._daily_ohlc = daily_ohlc
        self._levels = levels
        self._data = levels

        self._event_bus.publish(
            CPR_UPDATED,
            levels,
        )

        return levels

    def update(
        self,
        daily_ohlc: DailyOHLC,
    ) -> CPRLevels:
        """
        Backward-compatible alias for CPR calculation.
        """

        return self.calculate(daily_ohlc)

    def reset(self) -> None:
        """
        Clear accepted input, latest CPR levels, and readiness.
        """

        super().clear()

        self._daily_ohlc = None
        self._levels = None

    def clear(self) -> None:
        """
        Clear all CPR state and reset readiness.
        """

        self.reset()

    def _validate_daily_ohlc(self, daily_ohlc: DailyOHLC) -> None:
        if not isinstance(daily_ohlc, DailyOHLC):
            raise TypeError("CPREngine expects a DailyOHLC object.")

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
