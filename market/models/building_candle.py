"""
====================================================
Vision Trading OS
File: market/models/building_candle.py
====================================================

Mutable candle builder.

This object receives ticks and incrementally builds
an OHLCV candle. Once the candle is complete,
it is converted into an immutable Candle object.

Author : Vision Trading OS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from market.enums.exchange import Exchange
from market.enums.instrument import Instrument
from market.enums.timeframe import TimeFrame
from market.models.candle import Candle
from market.models.tick import Tick


@dataclass(slots=True)
class BuildingCandle:
    """
    Mutable candle under construction.
    """

    instrument: Instrument

    exchange: Exchange

    timeframe: TimeFrame

    start_time: datetime

    end_time: datetime

    open: float = field(init=False)

    high: float = field(init=False)

    low: float = field(init=False)

    close: float = field(init=False)

    volume: int = field(default=0)

    trade_count: int = field(default=0)

    open_interest: int | None = field(default=None)

    _pv_sum: float = field(default=0.0, repr=False)

    _initialized: bool = field(default=False, init=False)

    def update(self, tick: Tick) -> None:
        """
        Update candle with a new tick.
        """

        if tick.instrument != self.instrument:
            raise ValueError("Instrument mismatch.")

        if tick.exchange != self.exchange:
            raise ValueError("Exchange mismatch.")

        if not self._initialized:

            self.open = tick.price
            self.high = tick.price
            self.low = tick.price
            self.close = tick.price

            self._initialized = True

        else:

            self.high = max(self.high, tick.price)
            self.low = min(self.low, tick.price)
            self.close = tick.price

        self.volume += tick.volume

        self.trade_count += 1

        self.open_interest = tick.open_interest

        self._pv_sum += tick.price * tick.volume

    @property
    def vwap(self) -> float | None:
        """
        Current VWAP.
        """

        if self.volume == 0:
            return None

        return self._pv_sum / self.volume

    @property
    def is_initialized(self) -> bool:
        """
        Returns True after first tick.
        """

        return self._initialized

    def close(self) -> Candle:
        """
        Produce immutable candle.
        """

        if not self._initialized:
            raise RuntimeError(
                "Cannot close an empty candle."
            )

        return Candle(
            instrument=self.instrument,
            exchange=self.exchange,
            timeframe=self.timeframe,
            start_time=self.start_time,
            end_time=self.end_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            trade_count=self.trade_count,
            open_interest=self.open_interest,
            vwap=self.vwap,
        )

    def reset(self) -> None:
        """
        Reset builder.

        Used only by replay/testing.
        """

        self.volume = 0
        self.trade_count = 0
        self.open_interest = None
        self._pv_sum = 0.0
        self._initialized = False