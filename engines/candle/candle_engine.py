"""
====================================================
Vision Trading OS
Candle Engine
====================================================
"""

from __future__ import annotations

from collections.abc import Mapping
from collections import defaultdict
from datetime import timedelta

from core.base_engine import BaseEngine
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.events import (
    CANDLE_CLOSED,
    CANDLE_OPENED,
    CANDLE_UPDATED,
)
from core.models.building_candle import BuildingCandle
from core.models.candle import Candle
from core.models.tick import Tick


class CandleEngine(BaseEngine):
    """
    Builds live candles from incoming ticks for one timeframe.

    Candle Engine V1 assumes serialized, single-threaded
    tick delivery. Thread safety is provided upstream by the
    Market Data Engine.

    Responsibilities
    ----------------
    1. Receive Tick objects
    2. Maintain the active BuildingCandle per instrument
    3. Close completed candles into immutable Candle objects
    4. Publish candle lifecycle events
    """

    def __init__(
        self,
        event_bus,
        timeframe: TimeFrame = TimeFrame.ONE_MINUTE,
    ):

        if not isinstance(timeframe, TimeFrame):
            raise TypeError("timeframe must be a TimeFrame.")
        if not timeframe.is_intraday:
            raise ValueError("CandleEngine runtime candles require an intraday timeframe.")
        timeframe.duration

        super().__init__(event_bus)

        self.timeframe = timeframe
        self._current: dict[Instrument, BuildingCandle] = {}
        self._history: dict[Instrument, list[Candle]] = defaultdict(list)

    @property
    def current(self) -> dict[Instrument, BuildingCandle]:
        """
        Active candles keyed by instrument.
        """

        return self._current

    @property
    def history(self) -> dict[Instrument, list[Candle]]:
        """
        Closed candles keyed by instrument.
        """

        return self._history

    def on_tick(self, tick: Tick) -> BuildingCandle:
        """
        Process a new market tick.
        """

        current = self._current.get(tick.symbol)

        if current is None:
            return self._open_candle(tick)

        if current.is_same_candle(tick):
            current.update_from_tick(tick)

            self._event_bus.publish(
                CANDLE_UPDATED,
                current.copy(),
            )

            self._data = current

            return current

        self._close_candle(tick.symbol)

        return self._open_candle(tick)

    def update_tick(self, tick: Tick) -> BuildingCandle:
        """
        Backward-compatible alias for tick processing.
        """

        return self.on_tick(tick)

    def get_current(
        self,
        symbol: Instrument,
    ) -> BuildingCandle | None:
        """
        Return the active candle for an instrument.
        """

        return self._current.get(symbol)

    def get_history(
        self,
        symbol: Instrument,
    ) -> list[Candle]:
        """
        Return closed candles for an instrument.
        """

        return list(self._history[symbol])

    def seed_history(
        self,
        symbol: Instrument,
        candles: tuple[Candle, ...],
        *,
        replace: bool = False,
    ) -> tuple[Candle, ...]:
        """
        Seed closed historical candles without publishing live events.
        """

        if not isinstance(symbol, Instrument):
            raise TypeError("symbol must be Instrument")
        incoming = self._normalize_seed_candles(symbol, candles)
        current = self._current.get(symbol)
        if current is not None:
            for candle in incoming:
                if candle.start_time >= current.start_time:
                    raise ValueError("historical seed overlaps active candle")

        existing = tuple(self._history[symbol])
        if replace:
            proposed = incoming
            self._validate_strict_history(proposed)
            self._history[symbol] = list(proposed)
            return proposed

        existing_by_start = {candle.start_time: candle for candle in existing}
        accepted = []
        for candle in incoming:
            existing_candle = existing_by_start.get(candle.start_time)
            if existing_candle is not None:
                if existing_candle != candle:
                    raise ValueError("conflicting duplicate historical candle")
                continue
            if existing and candle.start_time < existing[-1].start_time:
                raise ValueError("historical seed cannot insert before latest history")
            accepted.append(candle)

        proposed = tuple(sorted((*existing, *accepted), key=lambda item: item.start_time))
        self._validate_strict_history(proposed)
        self._history[symbol] = list(proposed)
        return tuple(accepted)

    def clear(self) -> None:
        """
        Clear active and historical candle state.
        """

        super().clear()

        self._current.clear()
        self._history.clear()

    def _normalize_seed_candles(
        self,
        symbol: Instrument,
        candles,
    ) -> tuple[Candle, ...]:
        if isinstance(candles, (str, bytes, Mapping)):
            raise TypeError("candles must be an iterable of Candle values")
        try:
            incoming = tuple(candles)
        except TypeError as exc:
            raise TypeError("candles must be an iterable of Candle values") from exc

        by_start = {}
        for candle in incoming:
            self._validate_seed_candle(symbol, candle)
            existing = by_start.get(candle.start_time)
            if existing is not None and existing != candle:
                raise ValueError("conflicting duplicate historical candle")
            by_start[candle.start_time] = candle

        return tuple(sorted(by_start.values(), key=lambda item: item.start_time))

    def _validate_seed_candle(
        self,
        symbol: Instrument,
        candle: Candle,
    ) -> None:
        if not isinstance(candle, Candle):
            raise TypeError("historical seed items must be Candle values")
        if candle.symbol != symbol.value:
            raise ValueError("historical candle symbol does not match seed symbol")
        if candle.timeframe != self.timeframe.value:
            raise ValueError("historical candle timeframe does not match engine timeframe")
        for name in ("start_time", "end_time"):
            value = getattr(candle, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"historical candle {name} must be timezone-aware")
        if candle.start_time >= candle.end_time:
            raise ValueError("historical candle start_time must be before end_time")
        if candle.end_time - candle.start_time != self.timeframe.duration:
            raise ValueError("historical candle duration must match engine timeframe")

    def _validate_strict_history(self, candles: tuple[Candle, ...]) -> None:
        for previous, current in zip(candles, candles[1:]):
            if previous.start_time >= current.start_time:
                raise ValueError("historical candle history must be chronological and unique")
            if previous.end_time > current.start_time:
                raise ValueError("historical candle history must not overlap")

    def _open_candle(self, tick: Tick) -> BuildingCandle:
        candle = BuildingCandle.from_tick(
            tick,
            timeframe=self.timeframe,
        )

        self._current[tick.symbol] = candle
        self._data = candle

        self._event_bus.publish(
            CANDLE_OPENED,
            candle.copy(),
        )

        return candle

    def _close_candle(
        self,
        symbol: Instrument,
    ) -> Candle:
        current = self._current.get(symbol)

        if current is None:
            raise KeyError(
                f"No active candle found for {symbol.value}"
            )

        candle = current.close_candle()

        self._history[symbol].append(candle)
        self._data = candle

        try:
            self._event_bus.publish(
                CANDLE_CLOSED,
                candle,
            )
        finally:
            if self._current.get(symbol) is current:
                del self._current[symbol]

        return candle
