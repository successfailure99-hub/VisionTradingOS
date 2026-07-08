"""
====================================================
Vision Trading OS
Candle Model
====================================================
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Candle:

    symbol: str

    timeframe: str

    start_time: datetime

    end_time: datetime

    open: float

    high: float

    low: float

    close: float

    volume: int