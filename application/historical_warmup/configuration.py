"""
Historical warm-up configuration.
"""

from dataclasses import dataclass

from core.enums.timeframe import TimeFrame


@dataclass(frozen=True, slots=True)
class HistoricalWarmupConfiguration:
    timeframe: TimeFrame = TimeFrame.ONE_MINUTE
    warmup_candle_count: int = 375
    derive_previous_daily_ohlc: bool = True
    strict_gap_validation: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame")
        if self.timeframe is not TimeFrame.ONE_MINUTE:
            raise ValueError("Historical Warm-up V1 supports only one-minute candles")
        if isinstance(self.warmup_candle_count, bool) or not isinstance(self.warmup_candle_count, int):
            raise TypeError("warmup_candle_count must be a positive integer")
        if self.warmup_candle_count <= 0:
            raise ValueError("warmup_candle_count must be positive")
        if not isinstance(self.derive_previous_daily_ohlc, bool):
            raise TypeError("derive_previous_daily_ohlc must be bool")
        if not isinstance(self.strict_gap_validation, bool):
            raise TypeError("strict_gap_validation must be bool")
