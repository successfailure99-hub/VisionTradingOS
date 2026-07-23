"""
Stateful AI Reasoning Engine V2.
"""

from datetime import datetime
from threading import RLock
from typing import Any

from core.base_engine import BaseEngine
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import AI_REASONING_V2_READY, AI_REASONING_V2_UPDATED
from engines.ai_reasoning_v2.composer import AIReasoningV2Composer
from engines.ai_reasoning_v2.configuration import AIReasoningV2Configuration
from engines.ai_reasoning_v2.interpreter import AIReasoningV2Interpreter
from engines.ai_reasoning_v2.models import AIReasoningV2Input, AIReasoningV2Snapshot


AI_REASONING_V2_PARTIAL = "ai_reasoning_v2_partial"
AI_REASONING_V2_INVALID = "ai_reasoning_v2_invalid"
AI_REASONING_V2_FAILED = "ai_reasoning_v2_failed"
AI_REASONING_V2_STATE_UPDATED = "ai_reasoning_v2_state_updated"


class AIReasoningV2Engine(BaseEngine):
    """
    Deterministic AI reasoning over already-built intelligence snapshots.
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
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be Instrument")
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
        self._current_input: AIReasoningV2Input | None = None
        self._snapshot: AIReasoningV2Snapshot | None = None
        self._previous_snapshot: AIReasoningV2Snapshot | None = None
        self._history: tuple[AIReasoningV2Snapshot, ...] = ()
        self._updated_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error: str | None = None

    def process(
        self,
        multi_timeframe_evidence: Any,
        market_state: Any,
        setup_classification: Any,
        chart_explanation: Any,
        *,
        timestamp: datetime | None = None,
    ) -> AIReasoningV2Snapshot:
        with self._lock:
            try:
                input_contract = AIReasoningV2Input(
                    multi_timeframe_evidence=multi_timeframe_evidence,
                    market_state=market_state,
                    setup_classification=setup_classification,
                    chart_explanation=chart_explanation,
                    previous_reasoning=self._snapshot,
                )
                if input_contract.multi_timeframe_evidence.instrument.value != self.instrument.value:
                    self._last_error = "AI Reasoning V2 input instrument mismatch."
                    raise ValueError(self._last_error)
                output_timestamp = timestamp or input_contract.chart_explanation.timestamp
                _validate_output_timestamp(output_timestamp, input_contract)
                partial = _is_partial(input_contract, output_timestamp)
                previous = self._snapshot
                same_timestamp = (
                    self._current_input is not None
                    and output_timestamp == self._snapshot.timestamp
                    if self._snapshot is not None
                    else False
                )
                previous_for_reasoning = self._previous_snapshot if same_timestamp else previous
                input_contract = AIReasoningV2Input(
                    multi_timeframe_evidence=multi_timeframe_evidence,
                    market_state=market_state,
                    setup_classification=setup_classification,
                    chart_explanation=chart_explanation,
                    previous_reasoning=previous_for_reasoning,
                )
                snapshot = self._composer.compose(
                    inputs=input_contract,
                    configuration=self._configuration,
                    interpreter=self._interpreter,
                    timestamp=output_timestamp,
                )
                if _observable_fingerprint(snapshot, partial) == _observable_fingerprint(self._snapshot, partial):
                    return self._snapshot
            except (TypeError, ValueError):
                self._invalid_count += 1
                if self._last_error is None:
                    self._last_error = "AI Reasoning V2 input is invalid."
                self._event_bus.publish(AI_REASONING_V2_INVALID, self.snapshot)
                self._event_bus.publish(AI_REASONING_V2_STATE_UPDATED, self.snapshot)
                raise
            except Exception:
                self._failed_count += 1
                self._last_error = "AI Reasoning V2 failed."
                self._event_bus.publish(AI_REASONING_V2_FAILED, self.snapshot)
                self._event_bus.publish(AI_REASONING_V2_STATE_UPDATED, self.snapshot)
                raise

            if same_timestamp and self._history:
                history = self._history[:-1] + (snapshot,)
            else:
                self._previous_snapshot = previous
                history = self._history + (snapshot,)
            if len(history) > self._configuration.history_limit:
                history = history[-self._configuration.history_limit:]
            first = self._snapshot is None
            self._current_input = input_contract
            self._snapshot = snapshot
            self._history = history
            self._data = snapshot
            self._last_error = None
            if partial:
                self._partial_count += 1
                self._event_bus.publish(AI_REASONING_V2_PARTIAL, snapshot)
            else:
                self._updated_count += 1
                self._event_bus.publish(AI_REASONING_V2_UPDATED, snapshot)
            if first:
                self._event_bus.publish(AI_REASONING_V2_READY, snapshot)
            self._event_bus.publish(AI_REASONING_V2_STATE_UPDATED, self.snapshot)
            return snapshot

    def update(
        self,
        multi_timeframe_evidence: Any,
        market_state: Any,
        setup_classification: Any,
        chart_explanation: Any,
        *,
        timestamp: datetime | None = None,
    ) -> AIReasoningV2Snapshot:
        return self.process(
            multi_timeframe_evidence,
            market_state,
            setup_classification,
            chart_explanation,
            timestamp=timestamp,
        )

    @property
    def snapshot(self) -> AIReasoningV2Snapshot | None:
        return self._snapshot

    @property
    def previous_snapshot(self) -> AIReasoningV2Snapshot | None:
        return self._previous_snapshot

    @property
    def is_ready(self) -> bool:
        return self._snapshot is not None

    @property
    def updated_count(self) -> int:
        return self._updated_count

    @property
    def partial_count(self) -> int:
        return self._partial_count

    @property
    def invalid_count(self) -> int:
        return self._invalid_count

    @property
    def failed_count(self) -> int:
        return self._failed_count

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def history(self) -> tuple[AIReasoningV2Snapshot, ...]:
        return self._history

    def reset(self) -> None:
        with self._lock:
            super().clear()
            self._current_input = None
            self._snapshot = None
            self._previous_snapshot = None
            self._history = ()
            self._updated_count = 0
            self._partial_count = 0
            self._invalid_count = 0
            self._failed_count = 0
            self._last_error = None
            self._event_bus.publish(AI_REASONING_V2_STATE_UPDATED, self.snapshot)

    def clear(self) -> None:
        self.reset()


def _is_partial(inputs: AIReasoningV2Input, timestamp: datetime) -> bool:
    return (
        inputs.multi_timeframe_evidence.evidence_completeness.value != "complete"
        or inputs.market_state.evidence_quality.value in {"low", "insufficient"}
        or inputs.setup_classification.setup_quality.value == "low"
        or inputs.chart_explanation.explanation_quality.value == "low"
        or any((timestamp - item.timestamp).total_seconds() > 300 for item in _upstream(inputs))
    )


def _validate_output_timestamp(timestamp: datetime, inputs: AIReasoningV2Input) -> None:
    if not isinstance(timestamp, datetime):
        raise TypeError("timestamp must be datetime")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    if any(timestamp < item.timestamp for item in _upstream(inputs)):
        raise ValueError("AI Reasoning V2 timestamp cannot precede upstream intelligence")


def _upstream(inputs: AIReasoningV2Input) -> tuple[Any, ...]:
    return (
        inputs.multi_timeframe_evidence,
        inputs.market_state,
        inputs.setup_classification,
        inputs.chart_explanation,
    )


def _observable_fingerprint(snapshot: AIReasoningV2Snapshot | None, partial: bool) -> tuple[Any, ...] | None:
    if snapshot is None:
        return None
    return (
        snapshot.direction,
        snapshot.conviction,
        snapshot.reasoning_state,
        snapshot.change,
        snapshot.caution_severity,
        snapshot.headline,
        snapshot.summary,
        snapshot.primary_thesis,
        snapshot.supporting_points,
        snapshot.conflicting_points,
        snapshot.cautions,
        snapshot.watch_conditions,
        snapshot.confidence,
        snapshot.actionable_context,
        snapshot.rationale,
        partial,
    )
