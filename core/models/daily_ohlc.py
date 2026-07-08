"""
====================================================
Vision Trading OS
Daily OHLC Model
====================================================
"""

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True, frozen=True)
class DailyOHLC:
    """
    Previous trading day's OHLC.
    """

    trading_date: date

    open: float

    high: float

    low: float

    close: float