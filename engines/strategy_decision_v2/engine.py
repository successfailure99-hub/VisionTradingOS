from threading import RLock

from core.base_engine import BaseEngine
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import STRATEGY_DECISION_V2_READY, STRATEGY_DECISION_V2_UPDATED
from engines.market_context_v2.models import SUPPORTED_INSTRUMENTS
from engines.strategy_decision_v2.calculator import StrategyDecisionV2Calculator
from engines.strategy_decision_v2.configuration import StrategyDecisionV2Configuration
from engines.strategy_decision_v2.eligibility import StrategyEligibilityEvaluator
from engines.strategy_decision_v2.models import StrategyDecisionV2Input, StrategyDecisionV2Snapshot
from engines.strategy_decision_v2.selector import StrategySetupSelector


class StrategyDecisionV2Engine(BaseEngine):
    def __init__(
        self,
        *,
        instrument: Instrument,
        configuration: StrategyDecisionV2Configuration | None = None,
        eligibility: StrategyEligibilityEvaluator | None = None,
        selector: StrategySetupSelector | None = None,
        calculator: StrategyDecisionV2Calculator | None = None,
        event_bus: EventBus | None = None,
    ):
        if instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        super().__init__(event_bus or EventBus())
        self.instrument = instrument
        self._configuration = configuration or StrategyDecisionV2Configuration()
        self._eligibility = eligibility or StrategyEligibilityEvaluator()
        self._selector = selector or StrategySetupSelector()
        self._calculator = calculator or StrategyDecisionV2Calculator(self._eligibility, self._selector)
        self._lock = RLock()
        self._current_input: StrategyDecisionV2Input | None = None
        self._previous_distinct_input: StrategyDecisionV2Input | None = None
        self._snapshot: StrategyDecisionV2Snapshot | None = None
        self._previous_snapshot: StrategyDecisionV2Snapshot | None = None
        self._history: tuple[StrategyDecisionV2Snapshot, ...] = ()

    def process(self, inputs: StrategyDecisionV2Input) -> StrategyDecisionV2Snapshot:
        if not isinstance(inputs, StrategyDecisionV2Input):
            raise TypeError("inputs must be StrategyDecisionV2Input")
        if inputs.reasoning.instrument is not self.instrument:
            raise ValueError("Strategy Decision V2 input instrument mismatch")
        with self._lock:
            if self._current_input is not None:
                if inputs.reasoning.timestamp < self._current_input.reasoning.timestamp:
                    raise ValueError("stale Strategy Decision V2 input received")
                if inputs == self._current_input:
                    return self._snapshot
            first = self._snapshot is None
            same_timestamp = (
                self._current_input is not None
                and inputs.reasoning.timestamp == self._current_input.reasoning.timestamp
            )
            previous = self._previous_snapshot if same_timestamp else self._snapshot
            snapshot = self._calculator.calculate(
                inputs=inputs,
                configuration=self._configuration,
                previous=previous,
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
        self._event_bus.publish(STRATEGY_DECISION_V2_UPDATED, snapshot)
        if first:
            self._event_bus.publish(STRATEGY_DECISION_V2_READY, snapshot)
        return snapshot

    def update(self, inputs: StrategyDecisionV2Input) -> StrategyDecisionV2Snapshot:
        return self.process(inputs)

    @property
    def snapshot(self) -> StrategyDecisionV2Snapshot | None:
        return self._snapshot

    @property
    def previous_snapshot(self) -> StrategyDecisionV2Snapshot | None:
        return self._previous_snapshot

    @property
    def is_ready(self) -> bool:
        return self._snapshot is not None

    def history(self) -> tuple[StrategyDecisionV2Snapshot, ...]:
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
