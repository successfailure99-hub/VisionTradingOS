"""
Option Chain Analytics Engine V1.
"""

from datetime import date, datetime
from threading import RLock

from core.base_engine import BaseEngine
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from engines.option_chain.models import OptionChainSnapshot, OptionChainState
from engines.option_chain_analytics.calculator import OptionChainAnalyticsCalculator
from engines.option_chain_analytics.configuration import OptionChainAnalyticsConfiguration
from engines.option_chain_analytics.models import OptionChainAnalyticsSnapshot


class OptionChainAnalyticsEngine(BaseEngine):
    def __init__(
        self,
        *,
        underlying: Instrument,
        expiry: date,
        configuration: OptionChainAnalyticsConfiguration | None = None,
        calculator: OptionChainAnalyticsCalculator | None = None,
        event_bus=None,
    ):
        if not isinstance(underlying, Instrument):
            raise TypeError("underlying must be Instrument")
        if underlying not in {Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX}:
            raise ValueError("unsupported option analytics underlying")
        if not isinstance(expiry, date) or isinstance(expiry, datetime):
            raise TypeError("expiry must be date")
        super().__init__(event_bus or EventBus())
        self._underlying = underlying
        self._expiry = expiry
        self._configuration = configuration or OptionChainAnalyticsConfiguration()
        if not isinstance(self._configuration, OptionChainAnalyticsConfiguration):
            raise TypeError("configuration must be OptionChainAnalyticsConfiguration")
        self._calculator = calculator or OptionChainAnalyticsCalculator()
        if not isinstance(self._calculator, OptionChainAnalyticsCalculator):
            raise TypeError("calculator must be OptionChainAnalyticsCalculator")
        self._lock = RLock()
        self._source_snapshot: OptionChainSnapshot | None = None
        self._source_analysis: OptionChainState | None = None
        self._previous_distinct_snapshot: OptionChainSnapshot | None = None
        self._previous_distinct_analysis: OptionChainState | None = None
        self._snapshot: OptionChainAnalyticsSnapshot | None = None
        self._previous_snapshot: OptionChainAnalyticsSnapshot | None = None
        self._history: list[OptionChainAnalyticsSnapshot] = []

    def process(
        self,
        snapshot: OptionChainSnapshot,
        analysis: OptionChainState,
    ) -> OptionChainAnalyticsSnapshot:
        return self.update(snapshot, analysis)

    def update(
        self,
        snapshot: OptionChainSnapshot,
        analysis: OptionChainState,
    ) -> OptionChainAnalyticsSnapshot:
        with self._lock:
            self._validate_context(snapshot, analysis)
            if self._source_snapshot is not None:
                if snapshot.timestamp < self._source_snapshot.timestamp:
                    raise ValueError("stale option-chain analytics input")
                if snapshot == self._source_snapshot and analysis == self._source_analysis:
                    return self._snapshot
            same_timestamp_correction = (
                self._source_snapshot is not None
                and snapshot.timestamp == self._source_snapshot.timestamp
            )
            previous_snapshot = self._previous_distinct_snapshot if same_timestamp_correction else self._source_snapshot
            previous_analysis = self._previous_distinct_analysis if same_timestamp_correction else self._source_analysis
            analytics = self._calculator.calculate(
                current_snapshot=snapshot,
                current_analysis=analysis,
                previous_snapshot=previous_snapshot,
                previous_analysis=previous_analysis,
                configuration=self._configuration,
            )
            if not same_timestamp_correction and self._snapshot is not None:
                self._previous_snapshot = self._snapshot
                self._previous_distinct_snapshot = self._source_snapshot
                self._previous_distinct_analysis = self._source_analysis
            self._source_snapshot = snapshot
            self._source_analysis = analysis
            self._snapshot = analytics
            self._data = analytics
            if same_timestamp_correction and self._history:
                self._history[-1] = analytics
            else:
                self._history.append(analytics)
                if len(self._history) > self._configuration.history_limit:
                    self._history = self._history[-self._configuration.history_limit :]
            return analytics

    @property
    def snapshot(self) -> OptionChainAnalyticsSnapshot | None:
        return self._snapshot

    @property
    def previous_snapshot(self) -> OptionChainAnalyticsSnapshot | None:
        return self._previous_snapshot

    @property
    def is_ready(self) -> bool:
        return self._snapshot is not None

    def history(self) -> tuple[OptionChainAnalyticsSnapshot, ...]:
        with self._lock:
            return tuple(self._history)

    def reset(self) -> None:
        with self._lock:
            super().clear()
            self._source_snapshot = None
            self._source_analysis = None
            self._previous_distinct_snapshot = None
            self._previous_distinct_analysis = None
            self._snapshot = None
            self._previous_snapshot = None
            self._history.clear()

    def clear(self) -> None:
        self.reset()

    def _validate_context(self, snapshot, analysis) -> None:
        if not isinstance(snapshot, OptionChainSnapshot):
            raise TypeError("snapshot must be OptionChainSnapshot")
        if not isinstance(analysis, OptionChainState):
            raise TypeError("analysis must be OptionChainState")
        if snapshot.symbol != self._underlying.value or analysis.symbol != self._underlying.value:
            raise ValueError("option-chain analytics underlying mismatch")
        if snapshot.expiry_date != self._expiry or analysis.expiry_date != self._expiry:
            raise ValueError("option-chain analytics expiry mismatch")
        if snapshot.timestamp != analysis.timestamp:
            raise ValueError("option-chain analytics timestamp mismatch")
