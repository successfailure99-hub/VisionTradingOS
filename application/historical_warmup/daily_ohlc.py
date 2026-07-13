"""
Daily OHLC derivation from one-minute historical candles.
"""

from zoneinfo import ZoneInfo

from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC


_LOCAL_ZONE = ZoneInfo("Asia/Kolkata")


def derive_daily_ohlc(
    candles: tuple[Candle, ...],
    *,
    instrument: Instrument,
) -> DailyOHLC:
    if not isinstance(instrument, Instrument):
        raise TypeError("instrument must be Instrument")
    incoming = tuple(candles)
    if not incoming:
        raise ValueError("at least one candle is required")

    by_start = {}
    local_dates = set()
    for candle in incoming:
        if not isinstance(candle, Candle):
            raise TypeError("candles must contain Candle values")
        if candle.symbol != instrument.value:
            raise ValueError("candle instrument does not match")
        if candle.timeframe != TimeFrame.ONE_MINUTE.value:
            raise ValueError("daily OHLC derivation supports only one-minute candles")
        for name in ("start_time", "end_time"):
            value = getattr(candle, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"candle {name} must be timezone-aware")
        local_dates.add(candle.start_time.astimezone(_LOCAL_ZONE).date())
        existing = by_start.get(candle.start_time)
        if existing is not None and existing != candle:
            raise ValueError("conflicting duplicate historical candle")
        by_start[candle.start_time] = candle

    if len(local_dates) != 1:
        raise ValueError("candles must belong to one local trading date")

    ordered = tuple(sorted(by_start.values(), key=lambda item: item.start_time))
    return DailyOHLC(
        trading_date=ordered[0].start_time.astimezone(_LOCAL_ZONE).date(),
        open=ordered[0].open,
        high=max(candle.high for candle in ordered),
        low=min(candle.low for candle in ordered),
        close=ordered[-1].close,
    )
