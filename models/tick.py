"""
====================================================
Vision Trading OS
Tick Model
====================================================
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Tick:
    """
    One market update (tick).
    """

    symbol: str

    price: float

    volume: int

    timestamp: datetime