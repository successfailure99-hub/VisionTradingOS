"""
====================================================
Vision Trading OS
Market Snapshot
====================================================
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class MarketSnapshot:

    symbol: str

    last_price: float = 0.0

    open: float = 0.0

    high: float = 0.0

    low: float = 0.0

    close: float = 0.0

    volume: int = 0

    timestamp: datetime | None = None