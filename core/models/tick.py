"""
====================================================
Vision Trading OS
Tick Model
====================================================
"""

from dataclasses import dataclass
from datetime import datetime

from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


@dataclass(slots=True, frozen=True)
class Tick:
    """
    Represents one live market tick.

    Produced by:
        Market Data Engine

    Consumed by:
        Candle Engine
        VWAP Engine
        Dashboard
        AI Engine
    """

    symbol: Instrument

    exchange: Exchange

    timestamp: datetime

    last_price: float

    volume: int

    bid_price: float

    ask_price: float

    open_interest: int