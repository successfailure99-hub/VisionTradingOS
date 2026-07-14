"""
Stateful Risk Management Engine V2.
"""

from threading import RLock

from core.base_engine import BaseEngine
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import RISK_MANAGEMENT_V2_READY, RISK_MANAGEMENT_V2_UPDATED
from engines.market_context_v2.models import SUPPORTED_INSTRUMENTS
from engines.risk_management_v2.calculator import RiskManagementV2Calculator
from engines.risk_management_v2.configuration import RiskManagementV2Configuration
from engines.risk_management_v2.models import RiskManagementV2Input, RiskManagementV2Snapshot
from engines.risk_management_v2.sizing import PositionSizeCalculator
from engines.risk_management_v2.validator import RiskRuleValidator


class RiskManagementV2Engine(BaseEngine):
    def __init__(
        self,
        *,
        instrument: Instrument,
        configuration: RiskManagementV2Configuration | None = None,
        validator: RiskRuleValidator | None = None,
        sizing: PositionSizeCalculator | None = None,
        calculator: RiskManagementV2Calculator | None = None,
        event_bus: EventBus | None = None,
    ):
        if instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        super().__init__(event_bus or EventBus())
        self.instrument = instrument
        self._configuration = configuration or RiskManagementV2Configuration()
        self._validator = validator or RiskRuleValidator()
        self._sizing = sizing or PositionSizeCalculator()
        self._calculator = calculator or RiskManagementV2Calculator(self._validator, self._sizing)
        self._lock = RLock()
        self._current_input: RiskManagementV2Input | None = None
        self._previous_distinct_input: RiskManagementV2Input | None = None
        self._snapshot: RiskManagementV2Snapshot | None = None
        self._previous_snapshot: RiskManagementV2Snapshot | None = None
        self._history: tuple[RiskManagementV2Snapshot, ...] = ()

    def process(self, inputs: RiskManagementV2Input) -> RiskManagementV2Snapshot:
        if not isinstance(inputs, RiskManagementV2Input):
            raise TypeError("inputs must be RiskManagementV2Input")
        if inputs.strategy.instrument is not self.instrument:
            raise ValueError("Risk Management V2 input instrument mismatch")
        with self._lock:
            if self._current_input is not None:
                if inputs.strategy.timestamp < self._current_input.strategy.timestamp:
                    raise ValueError("stale Risk Management V2 input received")
                if inputs == self._current_input:
                    return self._snapshot
            first = self._snapshot is None
            same_timestamp = (
                self._current_input is not None
                and inputs.strategy.timestamp == self._current_input.strategy.timestamp
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
        self._event_bus.publish(RISK_MANAGEMENT_V2_UPDATED, snapshot)
        if first:
            self._event_bus.publish(RISK_MANAGEMENT_V2_READY, snapshot)
        return snapshot

    def update(self, inputs: RiskManagementV2Input) -> RiskManagementV2Snapshot:
        return self.process(inputs)

    @property
    def snapshot(self) -> RiskManagementV2Snapshot | None:
        return self._snapshot

    @property
    def previous_snapshot(self) -> RiskManagementV2Snapshot | None:
        return self._previous_snapshot

    @property
    def is_ready(self) -> bool:
        return self._snapshot is not None

    def history(self) -> tuple[RiskManagementV2Snapshot, ...]:
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
