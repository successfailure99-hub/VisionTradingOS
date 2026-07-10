"""
====================================================
Vision Trading OS
VWAP Levels
====================================================
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class VWAPLevels:
    """
    Stores the current VWAP values.
    """

    timestamp: datetime

    vwap: float

    upper_band_1: float
    upper_band_2: float
    upper_band_3: float

    lower_band_1: float
    lower_band_2: float
    lower_band_3: float