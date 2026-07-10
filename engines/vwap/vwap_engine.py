"""
====================================================
Vision Trading OS
VWAP Engine
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from core.base_engine import BaseEngine
from core.enums.instrument import Instrument
from core.events import VWAP_UPDATED
from core.models.tick import Tick
from engines.vwap.levels import VWAPLevels


@dataclass(slots=True)
class _VWAPAccumulator:
    trading_date: date
    cumulative_volume: int = 0
    cumulative_price_volume: float = 0.0
    last_tick: Tick | None = None
    latest: VWAPLevels | None = None


class VWAPEngine(BaseEngine):
    """
    Event-driven intraday VWAP calculator.

    VWAP Engine V1 assumes serialized, single-threaded calls to
    on_tick(). Thread safety and delivery serialization belong to
    the upstream orchestration layer. Internal locking and
    asynchronous processing are outside V1.

    Tick.volume is treated as incremental volume contributed by
    that tick, not cumulative day volume.
    """

    def __init__(self, event_bus):

        super().__init__(event_bus)

        self._state: dict[Instrument, _VWAPAccumulator] = {}

    def on_tick(self, tick: Tick) -> VWAPLevels | None:
        """
        Process one canonical Tick.

        Returns a new immutable VWAPLevels result when VWAP is
        updated. Returns None for exact duplicates and zero-volume
        ticks that do not create a new VWAP calculation.
        """

        self._validate_tick(tick)

        state = self._state.get(tick.symbol)
        trading_date = tick.timestamp.date()

        if state is None:
            state = _VWAPAccumulator(
                trading_date=trading_date,
            )
            self._state[tick.symbol] = state
        else:
            self._prepare_existing_state(
                tick,
                state,
                trading_date,
            )

        if state.last_tick == tick:
            return None

        state.last_tick = tick

        if tick.volume == 0:
            return None

        state.cumulative_price_volume += tick.last_price * tick.volume
        state.cumulative_volume += tick.volume

        result = VWAPLevels(
            symbol=tick.symbol,
            trading_date=trading_date,
            timestamp=tick.timestamp,
            vwap=(
                state.cumulative_price_volume
                / state.cumulative_volume
            ),
            cumulative_volume=state.cumulative_volume,
            cumulative_price_volume=state.cumulative_price_volume,
        )

        state.latest = result
        self._data = result

        self._event_bus.publish(
            VWAP_UPDATED,
            result,
        )

        return result

    def update_tick(self, tick: Tick) -> VWAPLevels | None:
        """
        Backward-compatible alias for tick processing.
        """

        return self.on_tick(tick)

    def get_latest(
        self,
        symbol: Instrument,
    ) -> VWAPLevels | None:
        """
        Return the latest valid VWAP result for an instrument.
        """

        state = self._state.get(symbol)

        if state is None:
            return None

        return state.latest

    def get_all_latest(self) -> dict[Instrument, VWAPLevels]:
        """
        Return a defensive copy of latest valid VWAP results.
        """

        return {
            symbol: state.latest
            for symbol, state in self._state.items()
            if state.latest is not None
        }

    def reset(self, symbol: Instrument) -> None:
        """
        Reset VWAP state for one instrument.
        """

        removed = self._state.pop(symbol, None)

        if removed is None:
            return

        if removed.latest is self._data:
            self._data = self._first_latest_result()

    def clear(self) -> None:
        """
        Clear all VWAP state and reset readiness.
        """

        super().clear()

        self._state.clear()

    def _prepare_existing_state(
        self,
        tick: Tick,
        state: _VWAPAccumulator,
        trading_date,
    ) -> None:
        if trading_date < state.trading_date:
            raise ValueError(
                "Stale VWAP tick received for "
                f"{tick.symbol.value}: "
                f"{trading_date.isoformat()} < "
                f"{state.trading_date.isoformat()}"
            )

        if trading_date > state.trading_date:
            state.trading_date = trading_date
            state.cumulative_volume = 0
            state.cumulative_price_volume = 0.0
            state.last_tick = None
            state.latest = None
            return

        if (
            state.last_tick is not None
            and tick.timestamp < state.last_tick.timestamp
        ):
            raise ValueError(
                "Stale VWAP tick received for "
                f"{tick.symbol.value}: "
                f"{tick.timestamp.isoformat()} < "
                f"{state.last_tick.timestamp.isoformat()}"
            )

    def _validate_tick(self, tick: Tick) -> None:
        if not isinstance(tick, Tick):
            raise TypeError("VWAPEngine expects a Tick object.")

        if not isinstance(tick.symbol, Instrument):
            raise ValueError("Tick symbol must be a supported Instrument.")

        if not isinstance(tick.timestamp, datetime):
            raise ValueError("Tick timestamp must be a datetime.")

        if tick.last_price <= 0:
            raise ValueError("Tick last_price must be greater than zero.")

        if tick.volume < 0:
            raise ValueError("Tick volume cannot be negative.")

    def _first_latest_result(self) -> VWAPLevels | None:
        for state in self._state.values():
            if state.latest is not None:
                return state.latest

        return None
