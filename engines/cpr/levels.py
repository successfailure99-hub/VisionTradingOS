"""
====================================================
Vision Trading OS
CPR Levels
====================================================
"""

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True, frozen=True)
class CPRLevels:
    """
    Stores CPR levels for one trading day.
    """

    trading_date: date

    previous_high: float
    previous_low: float
    previous_close: float

    pivot: float

    bc: float
    tc: float

    width: float

    width_percentage: float