"""
====================================================
Vision Trading OS
Building Candle
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from core.models.tick import Tick


INTRADAY_SESSION_OPEN = time(hour=9, minute=15)


@dataclass(slots=True)
class BuildingCandle:
    """
    Mutable candle used while constructing
    a live candle from incoming market ticks.

    Lifecycle

        Tick
          │
          ▼
    BuildingCandle
          │
          ▼
      Candle (immutable)

    Used by

    - Candle Engine
    """

    symbol: Instrument

    timeframe: TimeFrame

    start_time: datetime

    end_time: datetime

    open: float

    high: float

    low: float

    close: float

    volume: int = 0

    # -------------------------------------------------
    # Factory
    # -------------------------------------------------

    @classmethod
    def from_tick(
        cls,
        tick: Tick,
        timeframe: TimeFrame = TimeFrame.ONE_MINUTE,
    ) -> "BuildingCandle":
        """
        Create a new candle from the first tick.
        """

        duration = timeframe.duration
        seconds = int(duration.total_seconds())
        if seconds <= 0:
            raise ValueError("timeframe duration must be positive.")

        session_start = tick.timestamp.replace(
            hour=INTRADAY_SESSION_OPEN.hour,
            minute=INTRADAY_SESSION_OPEN.minute,
            second=0,
            microsecond=0,
        )
        elapsed_seconds = int((tick.timestamp - session_start).total_seconds())
        bucket_start_seconds = (elapsed_seconds // seconds) * seconds
        start = session_start + timedelta(seconds=bucket_start_seconds)
        end = start + duration

        return cls(
            symbol=tick.symbol,
            timeframe=timeframe,
            start_time=start,
            end_time=end,
            open=tick.last_price,
            high=tick.last_price,
            low=tick.last_price,
            close=tick.last_price,
            volume=tick.volume,
        )

    # -------------------------------------------------
    # Update
    # -------------------------------------------------

    def update_from_tick(self, tick: Tick) -> None:
        """
        Update OHLCV using a new tick.
        """

        price = tick.last_price

        if price > self.high:
            self.high = price

        if price < self.low:
            self.low = price

        self.close = price

        self.volume += tick.volume

    # -------------------------------------------------
    # Validation
    # -------------------------------------------------

    def is_same_candle(self, tick: Tick) -> bool:
        """
        True if tick belongs to this candle.
        """

        return (
            self.start_time
            <= tick.timestamp
            < self.end_time
        )

    # -------------------------------------------------
    # Conversion
    # -------------------------------------------------

    def close_candle(self) -> Candle:
        """
        Convert to immutable Candle.
        """

        return Candle(
            symbol=self.symbol.value,
            timeframe=self.timeframe.value,
            start_time=self.start_time,
            end_time=self.end_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )

    # -------------------------------------------------
    # Utility
    # -------------------------------------------------

    def copy(self) -> "BuildingCandle":
        """
        Return a mutable copy.
        """

        return BuildingCandle(
            symbol=self.symbol,
            timeframe=self.timeframe,
            start_time=self.start_time,
            end_time=self.end_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )
