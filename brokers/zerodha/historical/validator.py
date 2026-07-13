"""
Zerodha historical candle series validator.
"""

from collections.abc import Iterable, Mapping

from brokers.zerodha.historical.enums import HistoricalGapType
from brokers.zerodha.historical.intervals import interval_duration
from brokers.zerodha.historical.models import HistoricalGap
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle


class ZerodhaHistoricalSeriesValidator:
    def validate(
        self,
        candles: Iterable[Candle],
        *,
        timeframe: TimeFrame,
    ) -> tuple[
        tuple[Candle, ...],
        tuple[HistoricalGap, ...],
        int,
    ]:
        if isinstance(candles, (str, bytes, Mapping)):
            raise TypeError("candles must be an iterable of Candle values")
        if not isinstance(timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame")
        source = tuple(candles)
        if any(not isinstance(candle, Candle) for candle in source):
            raise TypeError("candles must contain Candle values")
        if not source:
            return (), (), 0
        if any(candle.timeframe != timeframe.value for candle in source):
            raise ValueError("candle timeframe must match requested timeframe")
        symbols = {candle.symbol for candle in source}
        if len(symbols) > 1:
            raise ValueError("all candles must have the same symbol")
        gaps: list[HistoricalGap] = []
        if any(source[index].start_time > source[index + 1].start_time for index in range(len(source) - 1)):
            gaps.append(HistoricalGap(HistoricalGapType.OUT_OF_ORDER, None, None, None, 0))
        by_time: dict[object, Candle] = {}
        duplicate_count = 0
        for candle in source:
            existing = by_time.get(candle.start_time)
            if existing is None:
                by_time[candle.start_time] = candle
                continue
            duplicate_count += 1
            if _signature(existing) != _signature(candle):
                raise ValueError("conflicting duplicate historical candle")
            gaps.append(HistoricalGap(HistoricalGapType.DUPLICATE_TIMESTAMP, candle.start_time, candle.start_time, candle.start_time, 0))
        unique = tuple(sorted(by_time.values(), key=lambda candle: candle.start_time))
        gaps.extend(_missing_gaps(unique, timeframe))
        return unique, tuple(gaps), duplicate_count


def _signature(candle: Candle) -> tuple:
    return (candle.open, candle.high, candle.low, candle.close, candle.volume, candle.end_time)


def _missing_gaps(candles: tuple[Candle, ...], timeframe: TimeFrame) -> list[HistoricalGap]:
    if timeframe is TimeFrame.DAILY:
        return []
    duration = interval_duration(timeframe)
    gaps = []
    for previous, current in zip(candles, candles[1:]):
        if previous.start_time.date() != current.start_time.date():
            continue
        expected = previous.start_time + duration
        if expected < current.start_time:
            missing = int((current.start_time - previous.start_time) / duration) - 1
            gaps.append(HistoricalGap(HistoricalGapType.MISSING_INTERVAL, expected, previous.start_time, current.start_time, missing))
    return gaps
