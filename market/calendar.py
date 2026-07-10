"""
====================================================
Vision Trading OS
File: market/calendar.py
====================================================

Market calendar.

Provides trading-day utilities used by every engine
within Vision Trading OS.

The calendar intentionally separates static trading
logic from exchange-specific holiday datasets.

Author : Vision Trading OS
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json


@dataclass(slots=True)
class MarketCalendar:
    """
    Exchange trading calendar.
    """

    holidays: set[date]

    # -------------------------------------------------
    # Trading Day
    # -------------------------------------------------

    def is_weekend(self, day: date) -> bool:
        """
        Saturday or Sunday.
        """

        return day.weekday() >= 5

    def is_holiday(self, day: date) -> bool:
        """
        Exchange holiday.
        """

        return day in self.holidays

    def is_trading_day(self, day: date) -> bool:
        """
        True if exchange is open.
        """

        return (
            not self.is_weekend(day)
            and not self.is_holiday(day)
        )

    # -------------------------------------------------
    # Previous Trading Day
    # -------------------------------------------------

    def previous_trading_day(
        self,
        day: date,
    ) -> date:

        current = day

        while True:

            current = current.fromordinal(
                current.toordinal() - 1
            )

            if self.is_trading_day(current):
                return current

    # -------------------------------------------------
    # Next Trading Day
    # -------------------------------------------------

    def next_trading_day(
        self,
        day: date,
    ) -> date:

        current = day

        while True:

            current = current.fromordinal(
                current.toordinal() + 1
            )

            if self.is_trading_day(current):
                return current

    # -------------------------------------------------
    # Loading
    # -------------------------------------------------

    @classmethod
    def from_json(
        cls,
        path: str | Path,
    ) -> "MarketCalendar":
        """
        Load holiday list from JSON.

        JSON Format

        [
            "2026-01-26",
            "2026-03-29"
        ]
        """

        file = Path(path)

        data = json.loads(
            file.read_text(
                encoding="utf-8"
            )
        )

        holidays = {

            date.fromisoformat(value)

            for value in data

        }

        return cls(holidays)