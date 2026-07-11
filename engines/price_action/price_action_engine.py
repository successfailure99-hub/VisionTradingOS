"""
Price Action Engine V1.
"""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from numbers import Real

from core.base_engine import BaseEngine
from core.events import PRICE_ACTION_READY
from core.models.candle import Candle
from engines.price_action.enums import BreakType, StructureType, SwingType, Trend
from engines.price_action.models import PriceActionState, StructureBreak, SwingPoint
from engines.price_action.swing_detector import SwingDetector


class PriceActionEngine(BaseEngine):
    """
    Deterministic market-structure engine for completed candles only.

    Price Action Engine V1 consumes immutable completed Candle objects
    for one externally managed symbol/timeframe context. Swing
    confirmation is delayed by right-side bars and uses strict
    inequality. Breaks are confirmed by candle close only; wick-only
    breaks are ignored.

    Calls are assumed serialized and single-threaded. Latest-candle
    correction is supported through deterministic replay. Historical
    persistence, multi-timeframe orchestration, indicators, advanced
    price-action concepts, and strategy interpretation are outside V1.
    """

    def __init__(
        self,
        event_bus,
        symbol: str,
        timeframe: str,
        left_bars: int = 2,
        right_bars: int = 2,
    ):
        super().__init__(event_bus)

        self._symbol = self._normalize_symbol(symbol)
        self._timeframe = self._normalize_timeframe(timeframe)
        self._left_bars = self._validate_bar_count("left_bars", left_bars)
        self._right_bars = self._validate_bar_count("right_bars", right_bars)

        self._candles: list[Candle] = []
        self._latest_swing_high: SwingPoint | None = None
        self._previous_swing_high: SwingPoint | None = None
        self._latest_swing_low: SwingPoint | None = None
        self._previous_swing_low: SwingPoint | None = None
        self._latest_break: StructureBreak | None = None
        self._trend = Trend.UNKNOWN
        self._broken_swing_levels: set[tuple[SwingType, int, float]] = set()

    @property
    def state(self) -> PriceActionState | None:
        return self._data

    @property
    def trend(self) -> Trend:
        return self._trend

    @property
    def latest_swing_high(self) -> SwingPoint | None:
        return self._latest_swing_high

    @property
    def latest_swing_low(self) -> SwingPoint | None:
        return self._latest_swing_low

    @property
    def latest_break(self) -> StructureBreak | None:
        return self._latest_break

    @property
    def candle_count(self) -> int:
        return len(self._candles)

    def update(self, candle: Candle) -> PriceActionState:
        self._validate_candle(candle)

        if not self._candles:
            state = self._accept_new_candle(candle)
            self._publish_state(state)
            return state

        latest = self._candles[-1]

        if candle == latest:
            return self._data

        if candle.start_time == latest.start_time:
            state = self._apply_latest_correction(candle)
            self._publish_state(state)
            return state

        if candle.start_time < latest.start_time:
            raise ValueError(
                "Stale Price Action candle received: "
                f"{candle.start_time.isoformat()} < "
                f"{latest.start_time.isoformat()}"
            )

        if candle.start_time < latest.end_time:
            raise ValueError(
                "Overlapping Price Action candle received: "
                f"{candle.start_time.isoformat()} < "
                f"{latest.end_time.isoformat()}"
            )

        state = self._accept_new_candle(candle)
        self._publish_state(state)
        return state

    def process(self, candle: Candle) -> PriceActionState:
        """
        Alias for update().
        """

        return self.update(candle)

    def reset(self) -> None:
        super().clear()
        self._reset_derived_state()
        self._candles.clear()

    def clear(self) -> None:
        self.reset()

    def _accept_new_candle(self, candle: Candle) -> PriceActionState:
        new_break = self._detect_break(candle)
        self._candles.append(candle)
        self._process_confirmable_swing()
        self._trend = self._determine_trend()
        if new_break is not None:
            self._latest_break = new_break

        state = self._make_state(candle)
        self._data = state
        return state

    def _apply_latest_correction(self, candle: Candle) -> PriceActionState:
        self._candles[-1] = candle
        candles = tuple(self._candles)
        self._data = None
        self._reset_derived_state()
        self._candles.clear()

        state = None
        for accepted in candles:
            state = self._accept_new_candle(accepted)

        return state

    def _process_confirmable_swing(self) -> None:
        swing = SwingDetector.detect_confirmed_swing(
            tuple(self._candles),
            self._left_bars,
            self._right_bars,
        )

        if swing is None:
            return

        if swing.swing_type is SwingType.HIGH:
            classified = self._classify_swing_high(swing)
            self._previous_swing_high = self._latest_swing_high
            self._latest_swing_high = classified
            return

        classified = self._classify_swing_low(swing)
        self._previous_swing_low = self._latest_swing_low
        self._latest_swing_low = classified

    def _classify_swing_high(self, swing: SwingPoint) -> SwingPoint:
        structure_type = None

        if self._latest_swing_high is not None:
            if swing.price > self._latest_swing_high.price:
                structure_type = StructureType.HIGHER_HIGH
            elif swing.price < self._latest_swing_high.price:
                structure_type = StructureType.LOWER_HIGH
            else:
                structure_type = StructureType.EQUAL_HIGH

        return self._replace_structure_type(swing, structure_type)

    def _classify_swing_low(self, swing: SwingPoint) -> SwingPoint:
        structure_type = None

        if self._latest_swing_low is not None:
            if swing.price > self._latest_swing_low.price:
                structure_type = StructureType.HIGHER_LOW
            elif swing.price < self._latest_swing_low.price:
                structure_type = StructureType.LOWER_LOW
            else:
                structure_type = StructureType.EQUAL_LOW

        return self._replace_structure_type(swing, structure_type)

    def _replace_structure_type(
        self,
        swing: SwingPoint,
        structure_type: StructureType | None,
    ) -> SwingPoint:
        return SwingPoint(
            symbol=swing.symbol,
            timeframe=swing.timeframe,
            swing_type=swing.swing_type,
            structure_type=structure_type,
            price=swing.price,
            candle_start_time=swing.candle_start_time,
            candle_end_time=swing.candle_end_time,
            candle_index=swing.candle_index,
        )

    def _determine_trend(self) -> Trend:
        high = self._latest_swing_high
        low = self._latest_swing_low

        if high is None or low is None:
            return Trend.UNKNOWN

        if high.structure_type is None or low.structure_type is None:
            return Trend.UNKNOWN

        if (
            high.structure_type is StructureType.HIGHER_HIGH
            and low.structure_type is StructureType.HIGHER_LOW
        ):
            return Trend.BULLISH

        if (
            high.structure_type is StructureType.LOWER_HIGH
            and low.structure_type is StructureType.LOWER_LOW
        ):
            return Trend.BEARISH

        return Trend.RANGE

    def _detect_break(self, candle: Candle) -> StructureBreak | None:
        bullish = None
        bearish = None

        if self._latest_swing_high is not None:
            key = self._swing_key(self._latest_swing_high)
            if key not in self._broken_swing_levels and candle.close > self._latest_swing_high.price:
                bullish = self._make_break(
                    candle,
                    self._latest_swing_high.price,
                    self._bullish_break_type(),
                )

        if self._latest_swing_low is not None:
            key = self._swing_key(self._latest_swing_low)
            if key not in self._broken_swing_levels and candle.close < self._latest_swing_low.price:
                bearish = self._make_break(
                    candle,
                    self._latest_swing_low.price,
                    self._bearish_break_type(),
                )

        if bullish is not None and bearish is not None:
            raise RuntimeError("Price Action state produced simultaneous two-sided break.")

        if bullish is not None:
            self._broken_swing_levels.add(self._swing_key(self._latest_swing_high))
            return bullish

        if bearish is not None:
            self._broken_swing_levels.add(self._swing_key(self._latest_swing_low))
            return bearish

        return None

    def _bullish_break_type(self) -> BreakType:
        if self._trend is Trend.BEARISH:
            return BreakType.BULLISH_CHOCH
        return BreakType.BULLISH_BOS

    def _bearish_break_type(self) -> BreakType:
        if self._trend is Trend.BULLISH:
            return BreakType.BEARISH_CHOCH
        return BreakType.BEARISH_BOS

    def _make_break(
        self,
        candle: Candle,
        broken_price: float,
        break_type: BreakType,
    ) -> StructureBreak:
        return StructureBreak(
            break_type=break_type,
            broken_price=broken_price,
            break_price=candle.close,
            candle_start_time=candle.start_time,
            candle_end_time=candle.end_time,
        )

    def _swing_key(self, swing: SwingPoint) -> tuple[SwingType, int, float]:
        return (swing.swing_type, swing.candle_index, swing.price)

    def _make_state(self, candle: Candle) -> PriceActionState:
        return PriceActionState(
            symbol=self._symbol,
            timeframe=self._timeframe,
            candle_count=len(self._candles),
            last_candle=candle,
            trend=self._trend,
            latest_swing_high=self._latest_swing_high,
            latest_swing_low=self._latest_swing_low,
            previous_swing_high=self._previous_swing_high,
            previous_swing_low=self._previous_swing_low,
            latest_break=self._latest_break,
        )

    def _publish_state(self, state: PriceActionState) -> None:
        self._event_bus.publish(PRICE_ACTION_READY, state)

    def _reset_derived_state(self) -> None:
        self._latest_swing_high = None
        self._previous_swing_high = None
        self._latest_swing_low = None
        self._previous_swing_low = None
        self._latest_break = None
        self._trend = Trend.UNKNOWN
        self._broken_swing_levels.clear()

    def _validate_candle(self, candle: Candle) -> None:
        if not isinstance(candle, Candle):
            raise TypeError("PriceActionEngine expects a Candle object.")

        if self._normalize_symbol(candle.symbol) != self._symbol:
            raise ValueError("Candle symbol does not match PriceActionEngine context.")

        if self._normalize_timeframe(candle.timeframe) != self._timeframe:
            raise ValueError("Candle timeframe does not match PriceActionEngine context.")

        if not isinstance(candle.start_time, datetime):
            raise ValueError("Candle start_time must be a datetime.")

        if not isinstance(candle.end_time, datetime):
            raise ValueError("Candle end_time must be a datetime.")

        if (candle.start_time.tzinfo is None) != (candle.end_time.tzinfo is None):
            raise ValueError("Candle start_time and end_time timezone awareness must match.")

        if candle.end_time <= candle.start_time:
            raise ValueError("Candle end_time must be greater than start_time.")

        self._validate_price("open", candle.open)
        self._validate_price("high", candle.high)
        self._validate_price("low", candle.low)
        self._validate_price("close", candle.close)

        if candle.high < candle.low:
            raise ValueError("Candle high must be greater than or equal to low.")

        if not candle.low <= candle.open <= candle.high:
            raise ValueError("Candle open must be within low and high.")

        if not candle.low <= candle.close <= candle.high:
            raise ValueError("Candle close must be within low and high.")

        if isinstance(candle.volume, bool) or not isinstance(candle.volume, int):
            raise ValueError("Candle volume must be an integer.")

        if candle.volume < 0:
            raise ValueError("Candle volume must be greater than or equal to zero.")

    def _validate_price(self, name: str, value: Real) -> None:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"Candle {name} must be a finite real number.")

        if not isfinite(value):
            raise ValueError(f"Candle {name} must be a finite real number.")

        if value <= 0:
            raise ValueError(f"Candle {name} must be greater than zero.")

    def _normalize_symbol(self, symbol: str) -> str:
        if not isinstance(symbol, str):
            raise ValueError("PriceActionEngine symbol must be a string.")

        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("PriceActionEngine symbol cannot be empty.")

        return normalized

    def _normalize_timeframe(self, timeframe: str) -> str:
        if not isinstance(timeframe, str):
            raise ValueError("PriceActionEngine timeframe must be a string.")

        normalized = timeframe.strip()
        if not normalized:
            raise ValueError("PriceActionEngine timeframe cannot be empty.")

        return normalized

    def _validate_bar_count(self, name: str, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"PriceActionEngine {name} must be an integer.")

        if value <= 0:
            raise ValueError(f"PriceActionEngine {name} must be greater than zero.")

        return value