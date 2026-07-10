"""
====================================================
Vision Trading OS
File: core/enums/timeframe.py
====================================================

Defines all supported market timeframes.

The TimeFrame enum is used by the Candle Engine,
aggregation engine, VWAP engine, Price Action engine,
and all strategy components.

Author : Vision Trading OS
"""

from __future__ import annotations

from enum import Enum
from datetime import timedelta


class TimeFrame(str, Enum):
    """
    Supported candle aggregation intervals.

    Enum values follow common trading notation.
    """

    # --------------------------------------------
    # Intraday
    # --------------------------------------------

    ONE_MINUTE = "1m"

    THREE_MINUTES = "3m"

    FIVE_MINUTES = "5m"

    TEN_MINUTES = "10m"

    FIFTEEN_MINUTES = "15m"

    THIRTY_MINUTES = "30m"

    ONE_HOUR = "60m"

    # --------------------------------------------
    # Higher Timeframes
    # --------------------------------------------

    DAILY = "1D"

    WEEKLY = "1W"

    MONTHLY = "1M"

    # -------------------------------------------------
    # Properties
    # -------------------------------------------------

    @property
    def is_intraday(self) -> bool:
        """
        Returns True if the timeframe belongs
        to the intraday category.
        """

        return self in {
            TimeFrame.ONE_MINUTE,
            TimeFrame.THREE_MINUTES,
            TimeFrame.FIVE_MINUTES,
            TimeFrame.TEN_MINUTES,
            TimeFrame.FIFTEEN_MINUTES,
            TimeFrame.THIRTY_MINUTES,
            TimeFrame.ONE_HOUR,
        }

    @property
    def is_higher_timeframe(self) -> bool:
        """
        Returns True for Daily and above.
        """

        return not self.is_intraday

    @property
    def duration(self) -> timedelta:
        """
        Duration represented by the timeframe.

        Returns
        -------
        timedelta

        Raises
        ------
        ValueError
            If the timeframe does not map
            to a fixed duration.
        """

        mapping = {
            TimeFrame.ONE_MINUTE: timedelta(minutes=1),
            TimeFrame.THREE_MINUTES: timedelta(minutes=3),
            TimeFrame.FIVE_MINUTES: timedelta(minutes=5),
            TimeFrame.TEN_MINUTES: timedelta(minutes=10),
            TimeFrame.FIFTEEN_MINUTES: timedelta(minutes=15),
            TimeFrame.THIRTY_MINUTES: timedelta(minutes=30),
            TimeFrame.ONE_HOUR: timedelta(hours=1),
            TimeFrame.DAILY: timedelta(days=1),
            TimeFrame.WEEKLY: timedelta(days=7),
        }

        if self not in mapping:
            raise ValueError(
                f"Duration is not fixed for {self.value}"
            )

        return mapping[self]

    @property
    def minutes(self) -> int:
        """
        Returns duration in minutes.

        Only valid for intraday timeframes.
        """

        if not self.is_intraday:
            raise ValueError(
                f"{self.value} is not an intraday timeframe."
            )

        return int(self.duration.total_seconds() // 60)

    @classmethod
    def from_value(cls, value: str) -> "TimeFrame":
        """
        Parse a timeframe string.

        Examples
        --------
        1m
        5m
        15m
        1D
        """

        normalized = value.strip()

        for timeframe in cls:
            if timeframe.value == normalized:
                return timeframe

        raise ValueError(
            f"Unsupported timeframe: {value}"
        )

    def __str__(self) -> str:
        """
        Human-readable representation.
        """

        return self.value