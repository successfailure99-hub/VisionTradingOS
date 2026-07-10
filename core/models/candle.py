"""
====================================================
Vision Trading OS
Candle Model
====================================================
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class Candle:
    """
    Represents one completed market candle.

    This model is used by:

    - Candle Engine
    - VWAP Engine
    - Price Action Engine
    - Dashboard
    - AI Engine
    """

    symbol: str

    timeframe: str

    start_time: datetime

    end_time: datetime

    open: float

    high: float

    low: float

    close: float

    volume: int