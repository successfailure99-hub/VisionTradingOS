"""
Zerodha historical interval mapping.
"""

from datetime import timedelta

from core.enums.timeframe import TimeFrame


INTERVALS = {
    TimeFrame.ONE_MINUTE: "minute",
    TimeFrame.THREE_MINUTES: "3minute",
    TimeFrame.FIVE_MINUTES: "5minute",
    TimeFrame.TEN_MINUTES: "10minute",
    TimeFrame.FIFTEEN_MINUTES: "15minute",
    TimeFrame.THIRTY_MINUTES: "30minute",
    TimeFrame.ONE_HOUR: "60minute",
    TimeFrame.DAILY: "day",
}

DURATIONS = {
    TimeFrame.ONE_MINUTE: timedelta(minutes=1),
    TimeFrame.THREE_MINUTES: timedelta(minutes=3),
    TimeFrame.FIVE_MINUTES: timedelta(minutes=5),
    TimeFrame.TEN_MINUTES: timedelta(minutes=10),
    TimeFrame.FIFTEEN_MINUTES: timedelta(minutes=15),
    TimeFrame.THIRTY_MINUTES: timedelta(minutes=30),
    TimeFrame.ONE_HOUR: timedelta(hours=1),
    TimeFrame.DAILY: timedelta(days=1),
}


def to_zerodha_interval(
    timeframe: TimeFrame,
) -> str:
    if not isinstance(timeframe, TimeFrame):
        raise TypeError("timeframe must be TimeFrame")
    if timeframe not in INTERVALS:
        raise ValueError(f"unsupported historical timeframe: {timeframe.value}")
    return INTERVALS[timeframe]


def interval_duration(
    timeframe: TimeFrame,
) -> timedelta:
    if not isinstance(timeframe, TimeFrame):
        raise TypeError("timeframe must be TimeFrame")
    if timeframe not in DURATIONS:
        raise ValueError(f"unsupported historical timeframe: {timeframe.value}")
    return DURATIONS[timeframe]
