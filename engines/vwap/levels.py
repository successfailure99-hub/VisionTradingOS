"""
====================================================
Vision Trading OS
VWAP Levels
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from core.enums.instrument import Instrument


@dataclass(slots=True, frozen=True)
class VWAPLevels:
    """
    Immutable session VWAP state for one instrument.
    """

    symbol: Instrument

    trading_date: date

    timestamp: datetime

    vwap: float

    cumulative_volume: int

    cumulative_price_volume: float
