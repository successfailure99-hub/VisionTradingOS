"""
====================================================
Vision Trading OS
Market Data Engine
====================================================
"""

from __future__ import annotations

from datetime import datetime

from core.base_engine import BaseEngine
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.events import MARKET_UPDATED, NEW_TICK
from core.models.tick import Tick


class MarketDataEngine(BaseEngine):
    """
    Canonical gateway for validated Tick objects.

    Market Data Engine V1 assumes serialized, single-threaded
    calls to on_tick(). Internal locks, worker threads, queues,
    and asyncio are outside V1. A later live-feed adapter or
    orchestrator will ensure serialized delivery.

    Responsibilities
    ----------------
    1. Validate canonical Tick objects
    2. Cache only the latest accepted Tick per instrument
    3. Ignore exact duplicate ticks
    4. Reject stale ticks per instrument
    5. Publish accepted ticks through the Event Bus
    """

    def __init__(self, event_bus):

        super().__init__(event_bus)

        self._latest: dict[Instrument, Tick] = {}

    def on_tick(self, tick: Tick) -> Tick | None:
        """
        Process an incoming Tick.

        Returns the accepted Tick. Returns None when the incoming
        tick is an exact duplicate of the latest accepted tick for
        that instrument. Raises ValueError for invalid or stale data.
        """

        self._validate_tick(tick)

        latest = self._latest.get(tick.symbol)

        if latest is not None:
            if tick == latest:
                return None

            if tick.timestamp < latest.timestamp:
                raise ValueError(
                    "Stale tick received for "
                    f"{tick.symbol.value}: "
                    f"{tick.timestamp.isoformat()} < "
                    f"{latest.timestamp.isoformat()}"
                )

        self._latest[tick.symbol] = tick
        self._data = tick

        self._event_bus.publish(
            NEW_TICK,
            tick,
        )
        self._event_bus.publish(
            MARKET_UPDATED,
            tick,
        )

        return tick

    def update_tick(self, tick: Tick) -> Tick | None:
        """
        Backward-compatible alias for tick processing.
        """

        return self.on_tick(tick)

    def get_latest(
        self,
        symbol: Instrument,
    ) -> Tick | None:
        """
        Return the latest accepted Tick for an instrument.
        """

        return self._latest.get(symbol)

    def get_all_latest(self) -> dict[Instrument, Tick]:
        """
        Return a defensive copy of latest ticks by instrument.
        """

        return dict(self._latest)

    def clear(self) -> None:
        """
        Clear all latest-tick state and reset readiness.
        """

        super().clear()

        self._latest.clear()

    def _validate_tick(self, tick: Tick) -> None:
        if not isinstance(tick, Tick):
            raise TypeError("MarketDataEngine expects a Tick object.")

        if not isinstance(tick.symbol, Instrument):
            raise ValueError("Tick symbol must be a supported Instrument.")

        if not isinstance(tick.exchange, Exchange):
            raise ValueError("Tick exchange must be a supported Exchange.")

        if not isinstance(tick.timestamp, datetime):
            raise ValueError("Tick timestamp must be a datetime.")

        if tick.last_price <= 0:
            raise ValueError("Tick last_price must be greater than zero.")

        if tick.volume < 0:
            raise ValueError("Tick volume cannot be negative.")

        if tick.bid_price < 0:
            raise ValueError("Tick bid_price cannot be negative.")

        if tick.ask_price < 0:
            raise ValueError("Tick ask_price cannot be negative.")

        if tick.open_interest < 0:
            raise ValueError("Tick open_interest cannot be negative.")

        if (
            tick.bid_price > 0
            and tick.ask_price > 0
            and tick.bid_price > tick.ask_price
        ):
            raise ValueError(
                "Tick bid_price cannot exceed ask_price."
            )
