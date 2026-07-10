"""
====================================================
Vision Trading OS
Candle Engine
====================================================
"""

from __future__ import annotations

from collections import defaultdict

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
    Builds live one-minute candles from incoming ticks.

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

        if timeframe != TimeFrame.ONE_MINUTE:
            raise NotImplementedError(
                "Candle Engine V1 supports only 1-minute candles."
            )

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

    def clear(self) -> None:
        """
        Clear active and historical candle state.
        """

        super().clear()

        self._current.clear()
        self._history.clear()

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
        current = self._current[symbol]
        candle = current.close_candle()

        self._history[symbol].append(candle)
        self._data = candle

        self._event_bus.publish(
            CANDLE_CLOSED,
            candle,
        )

        return candle
