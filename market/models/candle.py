"""
====================================================
Vision Trading OS
File: market/models/candle.py
====================================================

Immutable OHLCV candle model.

Completed candles are immutable and represent
historical market data. Candle creation is handled
by BuildingCandle.

Author : Vision Trading OS
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from market.enums.exchange import Exchange
from market.enums.instrument import Instrument
from market.enums.timeframe import TimeFrame


@dataclass(frozen=True, slots=True)
class Candle:
    """
    Immutable completed candle.
    """

    instrument: Instrument

    exchange: Exchange

    timeframe: TimeFrame

    start_time: datetime

    end_time: datetime

    open: float

    high: float

    low: float

    close: float

    volume: int

    trade_count: int = 0

    open_interest: int | None = None

    vwap: float | None = None

    def __post_init__(self) -> None:
        """
        Validate candle integrity.
        """

        prices = (
            self.open,
            self.high,
            self.low,
            self.close,
        )

        for value in prices:
            if value <= 0:
                raise ValueError(
                    "OHLC values must be greater than zero."
                )

        if self.high < max(
            self.open,
            self.close,
            self.low,
        ):
            raise ValueError(
                "High must be the highest price."
            )

        if self.low > min(
            self.open,
            self.close,
            self.high,
        ):
            raise ValueError(
                "Low must be the lowest price."
            )

        if self.volume < 0:
            raise ValueError(
                "Volume cannot be negative."
            )

        if self.trade_count < 0:
            raise ValueError(
                "Trade count cannot be negative."
            )

        if self.end_time <= self.start_time:
            raise ValueError(
                "End time must be after start time."
            )

    @property
    def body(self) -> float:
        """
        Absolute candle body size.
        """

        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        """
        Total candle range.
        """

        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        """
        Upper shadow length.
        """

        return self.high - max(
            self.open,
            self.close,
        )

    @property
    def lower_wick(self) -> float:
        """
        Lower shadow length.
        """

        return min(
            self.open,
            self.close,
        ) - self.low

    @property
    def is_bullish(self) -> bool:
        """
        True if close > open.
        """

        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        """
        True if close < open.
        """

        return self.close < self.open

    @property
    def is_doji(self) -> bool:
        """
        Detect doji candles.

        A candle is considered a doji when the body
        is less than or equal to 10% of the total range.
        """

        if self.range == 0:
            return True

        return (self.body / self.range) <= 0.10

    @property
    def midpoint(self) -> float:
        """
        Midpoint of the candle.
        """

        return (self.high + self.low) / 2

    def __str__(self) -> str:
        """
        Human-readable representation.
        """

        return (
            f"{self.instrument.value} "
            f"{self.timeframe.value} "
            f"O:{self.open:.2f} "
            f"H:{self.high:.2f} "
            f"L:{self.low:.2f} "
            f"C:{self.close:.2f}"
        )