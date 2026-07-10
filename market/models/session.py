"""
====================================================
Vision Trading OS
File: market/models/session.py
====================================================

Trading session model.

Defines a market trading session and provides helper
methods for session-aware processing.

Author : Vision Trading OS
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time


@dataclass(frozen=True, slots=True)
class TradingSession:
    """
    Immutable trading session definition.
    """

    name: str

    open_time: time

    close_time: time

    pre_open_time: time | None = None

    post_close_time: time | None = None

    def contains(self, timestamp: datetime) -> bool:
        """
        True if the timestamp falls inside the trading session.
        """

        current = timestamp.time()

        return self.open_time <= current < self.close_time

    def is_pre_open(self, timestamp: datetime) -> bool:
        """
        True if timestamp belongs to the pre-open session.
        """

        if self.pre_open_time is None:
            return False

        current = timestamp.time()

        return self.pre_open_time <= current < self.open_time

    def is_post_close(self, timestamp: datetime) -> bool:
        """
        True if timestamp belongs to the post-close session.
        """

        if self.post_close_time is None:
            return False

        current = timestamp.time()

        return self.close_time <= current < self.post_close_time

    @property
    def duration_minutes(self) -> int:
        """
        Trading session duration in minutes.
        """

        open_minutes = (
            self.open_time.hour * 60
            + self.open_time.minute
        )

        close_minutes = (
            self.close_time.hour * 60
            + self.close_time.minute
        )

        return close_minutes - open_minutes

    def __str__(self) -> str:
        return (
            f"{self.name} "
            f"({self.open_time} - {self.close_time})"
        )


# -----------------------------------------------------
# Default NSE Cash Session
# -----------------------------------------------------

NSE_CASH_SESSION = TradingSession(
    name="NSE Cash Market",
    pre_open_time=time(9, 0),
    open_time=time(9, 15),
    close_time=time(15, 30),
    post_close_time=time(16, 0),
)