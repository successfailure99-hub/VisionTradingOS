"""
Stateful Market Context Engine V2 wrapper.
"""

from threading import RLock

from core.base_engine import BaseEngine
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import MARKET_CONTEXT_V2_READY, MARKET_CONTEXT_V2_UPDATED
from engines.market_context_v2.calculator import MarketContextV2Calculator
from engines.market_context_v2.configuration import MarketContextV2Configuration
from engines.market_context_v2.models import (
    SUPPORTED_INSTRUMENTS,
    MarketContextV2Input,
    MarketContextV2Snapshot,
)


class MarketContextV2Engine(BaseEngine):
    """
    Deterministic Market Context Engine V2.
    """

    def __init__(
        self,
        *,
        instrument: Instrument,
        configuration: MarketContextV2Configuration | None = None,
        calculator: MarketContextV2Calculator | None = None,
        event_bus: EventBus | None = None,
    ):
        if instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        super().__init__(event_bus or EventBus())
        self.instrument = instrument
        self._configuration = configuration or MarketContextV2Configuration()
        if not isinstance(self._configuration, MarketContextV2Configuration):
            raise TypeError("configuration must be MarketContextV2Configuration")
        self._calculator = calculator or MarketContextV2Calculator()
        if not isinstance(self._calculator, MarketContextV2Calculator):
            raise TypeError("calculator must be MarketContextV2Calculator")
        self._lock = RLock()
        self._current_input: MarketContextV2Input | None = None
        self._previous_distinct_input: MarketContextV2Input | None = None
        self._snapshot: MarketContextV2Snapshot | None = None
        self._previous_snapshot: MarketContextV2Snapshot | None = None
        self._history: tuple[MarketContextV2Snapshot, ...] = ()

    def process(
        self,
        inputs: MarketContextV2Input,
    ) -> MarketContextV2Snapshot:
        if not isinstance(inputs, MarketContextV2Input):
            raise TypeError("inputs must be MarketContextV2Input")
        if inputs.instrument is not self.instrument:
            raise ValueError("Market Context V2 input instrument mismatch")

        with self._lock:
            if self._current_input is not None:
                if inputs.timestamp < self._current_input.timestamp:
                    raise ValueError("stale Market Context V2 input received")
                if inputs == self._current_input:
                    return self._snapshot

            first = self._snapshot is None
            same_timestamp = (
                self._current_input is not None
                and inputs.timestamp == self._current_input.timestamp
            )
            snapshot = self._calculator.calculate(
                inputs=inputs,
                configuration=self._configuration,
            )

            if same_timestamp:
                history = self._history[:-1] + (snapshot,)
            else:
                self._previous_distinct_input = self._current_input
                self._previous_snapshot = self._snapshot
                history = self._history + (snapshot,)

            if len(history) > self._configuration.history_limit:
                history = history[-self._configuration.history_limit:]

            self._current_input = inputs
            self._snapshot = snapshot
            self._history = history
            self._data = snapshot

        self._event_bus.publish(MARKET_CONTEXT_V2_UPDATED, snapshot)
        if first:
            self._event_bus.publish(MARKET_CONTEXT_V2_READY, snapshot)
        return snapshot

    def update(
        self,
        inputs: MarketContextV2Input,
    ) -> MarketContextV2Snapshot:
        return self.process(inputs)

    @property
    def snapshot(self) -> MarketContextV2Snapshot | None:
        return self._snapshot

    @property
    def previous_snapshot(self) -> MarketContextV2Snapshot | None:
        return self._previous_snapshot

    @property
    def is_ready(self) -> bool:
        return self._snapshot is not None

    def history(self) -> tuple[MarketContextV2Snapshot, ...]:
        return self._history

    def reset(self) -> None:
        with self._lock:
            super().clear()
            self._current_input = None
            self._previous_distinct_input = None
            self._snapshot = None
            self._previous_snapshot = None
            self._history = ()

    def clear(self) -> None:
        self.reset()
