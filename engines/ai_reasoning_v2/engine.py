"""
Stateful AI Reasoning Engine V2.
"""

from threading import RLock

from core.base_engine import BaseEngine
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import AI_REASONING_V2_READY, AI_REASONING_V2_UPDATED
from engines.ai_reasoning_v2.composer import AIReasoningV2Composer
from engines.ai_reasoning_v2.configuration import AIReasoningV2Configuration
from engines.ai_reasoning_v2.interpreter import AIReasoningV2Interpreter
from engines.ai_reasoning_v2.models import AIReasoningV2Input, AIReasoningV2Snapshot
from engines.market_context_v2.models import SUPPORTED_INSTRUMENTS, MarketContextV2Snapshot


class AIReasoningV2Engine(BaseEngine):
    """
    Deterministic reasoning engine for one Market Context V2 instrument.
    """

    def __init__(
        self,
        *,
        instrument: Instrument,
        configuration: AIReasoningV2Configuration | None = None,
        interpreter: AIReasoningV2Interpreter | None = None,
        composer: AIReasoningV2Composer | None = None,
        event_bus: EventBus | None = None,
    ):
        if instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        super().__init__(event_bus or EventBus())
        self.instrument = instrument
        self._configuration = configuration or AIReasoningV2Configuration()
        self._interpreter = interpreter or AIReasoningV2Interpreter()
        self._composer = composer or AIReasoningV2Composer()
        if not isinstance(self._configuration, AIReasoningV2Configuration):
            raise TypeError("configuration must be AIReasoningV2Configuration")
        if not isinstance(self._interpreter, AIReasoningV2Interpreter):
            raise TypeError("interpreter must be AIReasoningV2Interpreter")
        if not isinstance(self._composer, AIReasoningV2Composer):
            raise TypeError("composer must be AIReasoningV2Composer")
        self._lock = RLock()
        self._current_context: MarketContextV2Snapshot | None = None
        self._previous_distinct_context: MarketContextV2Snapshot | None = None
        self._snapshot: AIReasoningV2Snapshot | None = None
        self._previous_snapshot: AIReasoningV2Snapshot | None = None
        self._history: tuple[AIReasoningV2Snapshot, ...] = ()

    def process(self, context: MarketContextV2Snapshot) -> AIReasoningV2Snapshot:
        if not isinstance(context, MarketContextV2Snapshot):
            raise TypeError("context must be MarketContextV2Snapshot")
        if context.instrument is not self.instrument:
            raise ValueError("AI Reasoning V2 context instrument mismatch")
        with self._lock:
            if self._current_context is not None:
                if context.timestamp < self._current_context.timestamp:
                    raise ValueError("stale AI Reasoning V2 context received")
                if context == self._current_context:
                    return self._snapshot

            first = self._snapshot is None
            same_timestamp = (
                self._current_context is not None
                and context.timestamp == self._current_context.timestamp
            )
            previous_for_reasoning = (
                self._previous_snapshot if same_timestamp else self._snapshot
            )
            snapshot = self._composer.compose(
                inputs=AIReasoningV2Input(
                    context=context,
                    previous_reasoning=previous_for_reasoning,
                ),
                configuration=self._configuration,
                interpreter=self._interpreter,
            )
            if same_timestamp:
                history = self._history[:-1] + (snapshot,)
            else:
                self._previous_distinct_context = self._current_context
                self._previous_snapshot = self._snapshot
                history = self._history + (snapshot,)
            if len(history) > self._configuration.history_limit:
                history = history[-self._configuration.history_limit:]
            self._current_context = context
            self._snapshot = snapshot
            self._history = history
            self._data = snapshot

        self._event_bus.publish(AI_REASONING_V2_UPDATED, snapshot)
        if first:
            self._event_bus.publish(AI_REASONING_V2_READY, snapshot)
        return snapshot

    def update(self, context: MarketContextV2Snapshot) -> AIReasoningV2Snapshot:
        return self.process(context)

    @property
    def snapshot(self) -> AIReasoningV2Snapshot | None:
        return self._snapshot

    @property
    def previous_snapshot(self) -> AIReasoningV2Snapshot | None:
        return self._previous_snapshot

    @property
    def is_ready(self) -> bool:
        return self._snapshot is not None

    def history(self) -> tuple[AIReasoningV2Snapshot, ...]:
        return self._history

    def reset(self) -> None:
        with self._lock:
            super().clear()
            self._current_context = None
            self._previous_distinct_context = None
            self._snapshot = None
            self._previous_snapshot = None
            self._history = ()

    def clear(self) -> None:
        self.reset()
