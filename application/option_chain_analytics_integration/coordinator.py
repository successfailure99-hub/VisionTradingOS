"""
Synchronous integration coordinator for option-chain analytics.
"""

from datetime import UTC, datetime
from threading import RLock

from application.enums import RuntimeStatus
from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_option_chain_integration import (
    LiveOptionChainIntegrationCoordinator,
    LiveOptionChainIntegrationSnapshot,
)
from application.option_chain_analytics_integration.adapters import (
    analytics_input_from_live_integration_snapshot,
)
from application.option_chain_analytics_integration.configuration import (
    OptionChainAnalyticsIntegrationConfiguration,
)
from application.option_chain_analytics_integration.enums import (
    OptionChainAnalyticsIntegrationStatus,
    OptionChainAnalyticsProcessingResult,
)
from application.option_chain_analytics_integration.models import (
    OptionChainAnalyticsIntegrationSnapshot,
    OptionChainAnalyticsProcessingOutcome,
)
from core.enums.instrument import Instrument
from engines.option_chain_analytics import OptionChainAnalyticsEngine


class OptionChainAnalyticsIntegrationCoordinator:
    def __init__(
        self,
        *,
        lifecycle: ApplicationLifecycleManager,
        live_option_chain_integration: LiveOptionChainIntegrationCoordinator,
        analytics_engine: OptionChainAnalyticsEngine,
        configuration: OptionChainAnalyticsIntegrationConfiguration | None = None,
        clock=None,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be ApplicationLifecycleManager")
        if not isinstance(live_option_chain_integration, LiveOptionChainIntegrationCoordinator):
            raise TypeError("live_option_chain_integration must be LiveOptionChainIntegrationCoordinator")
        if not isinstance(analytics_engine, OptionChainAnalyticsEngine):
            raise TypeError("analytics_engine must be OptionChainAnalyticsEngine")
        self._lifecycle = lifecycle
        self._live_option_chain_integration = live_option_chain_integration
        self._analytics_engine = analytics_engine
        self._configuration = configuration or OptionChainAnalyticsIntegrationConfiguration()
        if not isinstance(self._configuration, OptionChainAnalyticsIntegrationConfiguration):
            raise TypeError("configuration must be OptionChainAnalyticsIntegrationConfiguration")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = RLock()
        self._status = OptionChainAnalyticsIntegrationStatus.CREATED
        self._validation_count = 0
        self._start_count = 0
        self._stop_count = 0
        self._processing_count = 0
        self._analytics_update_count = 0
        self._duplicate_count = 0
        self._not_ready_count = 0
        self._last_started_at: datetime | None = None
        self._last_stopped_at: datetime | None = None
        self._last_processed_at: datetime | None = None
        self._last_outcome: OptionChainAnalyticsProcessingOutcome | None = None
        self._last_error: str | None = None
        if self._live_option_chain_integration.lifecycle is not self._lifecycle:
            raise ValueError("live option-chain integration must use the same lifecycle")

    @property
    def lifecycle(self) -> ApplicationLifecycleManager:
        return self._lifecycle

    @property
    def live_option_chain_integration(
        self,
    ) -> LiveOptionChainIntegrationCoordinator:
        return self._live_option_chain_integration

    @property
    def analytics_engine(self) -> OptionChainAnalyticsEngine:
        return self._analytics_engine

    def validate(self) -> OptionChainAnalyticsIntegrationSnapshot:
        with self._lock:
            self._status = OptionChainAnalyticsIntegrationStatus.VALIDATING
            try:
                lifecycle_snapshot = self._lifecycle.snapshot()
                live_snapshot = self._live_option_chain_integration.snapshot()
                self._validate_snapshots(lifecycle_snapshot, live_snapshot)
            except Exception as exc:
                self._status = OptionChainAnalyticsIntegrationStatus.ERROR
                self._last_error = _safe_error(exc)
                raise
            self._validation_count += 1
            self._last_error = None
            self._status = OptionChainAnalyticsIntegrationStatus.READY
            return self._build_snapshot(lifecycle_snapshot, live_snapshot)

    def start(self) -> OptionChainAnalyticsIntegrationSnapshot:
        with self._lock:
            if self._status is OptionChainAnalyticsIntegrationStatus.RUNNING:
                return self.snapshot()
            try:
                self.validate()
                self._status = OptionChainAnalyticsIntegrationStatus.STARTING
                started_at = self._now()
            except Exception as exc:
                self._status = OptionChainAnalyticsIntegrationStatus.ERROR
                self._last_error = _safe_error(exc)
                raise
            self._start_count += 1
            self._last_started_at = started_at
            self._last_error = None
            self._status = OptionChainAnalyticsIntegrationStatus.RUNNING
            return self.snapshot()

    def stop(self) -> OptionChainAnalyticsIntegrationSnapshot:
        with self._lock:
            if self._status in {
                OptionChainAnalyticsIntegrationStatus.CREATED,
                OptionChainAnalyticsIntegrationStatus.STOPPED,
                OptionChainAnalyticsIntegrationStatus.CLEARED,
            }:
                self._status = OptionChainAnalyticsIntegrationStatus.STOPPED
                return self.snapshot()
            try:
                self._status = OptionChainAnalyticsIntegrationStatus.STOPPING
                stopped_at = self._now()
            except Exception as exc:
                self._status = OptionChainAnalyticsIntegrationStatus.ERROR
                self._last_error = _safe_error(exc)
                raise
            self._stop_count += 1
            self._last_stopped_at = stopped_at
            self._last_error = None
            self._status = OptionChainAnalyticsIntegrationStatus.STOPPED
            return self.snapshot()

    def restart(self) -> OptionChainAnalyticsIntegrationSnapshot:
        with self._lock:
            self.stop()
            self.validate()
            return self.start()

    def process_current(
        self,
    ) -> OptionChainAnalyticsProcessingOutcome:
        self._require_running()
        live_snapshot = self._live_option_chain_integration.snapshot()
        return self.process_live_snapshot(live_snapshot)

    def process_live_snapshot(
        self,
        snapshot: LiveOptionChainIntegrationSnapshot,
    ) -> OptionChainAnalyticsProcessingOutcome:
        with self._lock:
            self._require_running()
            if not isinstance(snapshot, LiveOptionChainIntegrationSnapshot):
                raise TypeError("snapshot must be LiveOptionChainIntegrationSnapshot")
            completed_at = self._now()
            if self._configuration.process_only_ready_live_snapshots and not _is_processable(snapshot):
                outcome = OptionChainAnalyticsProcessingOutcome(
                    result=OptionChainAnalyticsProcessingResult.NOT_READY,
                    processed=False,
                    analytics_updated=False,
                    source_timestamp=None,
                    analytics_snapshot=None,
                    completed_at=completed_at,
                )
                self._not_ready_count += 1
                self._last_outcome = outcome
                self._last_processed_at = completed_at
                return outcome
            try:
                source_snapshot, source_analysis = analytics_input_from_live_integration_snapshot(snapshot)
                previous = self._analytics_engine.snapshot
                analytics = self._analytics_engine.process(source_snapshot, source_analysis)
            except Exception as exc:
                self._last_error = _safe_error(exc)
                raise
            updated = analytics is not previous
            result = (
                OptionChainAnalyticsProcessingResult.PROCESSED
                if updated
                else OptionChainAnalyticsProcessingResult.DUPLICATE
            )
            outcome = OptionChainAnalyticsProcessingOutcome(
                result=result,
                processed=True,
                analytics_updated=updated,
                source_timestamp=source_snapshot.timestamp,
                analytics_snapshot=analytics,
                completed_at=completed_at,
            )
            self._processing_count += 1
            if updated:
                self._analytics_update_count += 1
            else:
                self._duplicate_count += 1
            self._last_processed_at = completed_at
            self._last_outcome = outcome
            self._last_error = None
            return outcome

    def snapshot(self) -> OptionChainAnalyticsIntegrationSnapshot:
        with self._lock:
            lifecycle_snapshot = self._lifecycle.snapshot()
            live_snapshot = self._live_option_chain_integration.snapshot()
            return self._build_snapshot(lifecycle_snapshot, live_snapshot)

    def clear(self) -> OptionChainAnalyticsIntegrationSnapshot:
        with self._lock:
            if self._status is not OptionChainAnalyticsIntegrationStatus.STOPPED:
                raise RuntimeError("clear requires stopped analytics integration")
            if self._configuration.reset_analytics_on_clear:
                self._analytics_engine.reset()
            self._validation_count = 0
            self._start_count = 0
            self._stop_count = 0
            self._processing_count = 0
            self._analytics_update_count = 0
            self._duplicate_count = 0
            self._not_ready_count = 0
            self._last_started_at = None
            self._last_stopped_at = None
            self._last_processed_at = None
            self._last_outcome = None
            self._last_error = None
            self._status = OptionChainAnalyticsIntegrationStatus.CLEARED
            return self.snapshot()

    def _validate_snapshots(self, lifecycle_snapshot, live_snapshot) -> None:
        if (
            self._configuration.require_application_running
            and lifecycle_snapshot.status is not RuntimeStatus.RUNNING
        ):
            raise RuntimeError("application lifecycle must be RUNNING")
        if (
            self._configuration.require_live_option_integration_running
            and not live_snapshot.running
        ):
            raise RuntimeError("live option-chain integration must be RUNNING")
        if live_snapshot.underlying not in {Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX}:
            raise ValueError("unsupported option-chain analytics underlying")

    def _build_snapshot(self, lifecycle_snapshot, live_snapshot) -> OptionChainAnalyticsIntegrationSnapshot:
        history = self._analytics_engine.history()
        latest = self._analytics_engine.snapshot
        application_ready = (
            not self._configuration.require_application_running
            or lifecycle_snapshot.status is RuntimeStatus.RUNNING
        )
        live_ready = (
            not self._configuration.require_live_option_integration_running
            or live_snapshot.running
        )
        ready = (
            self._status
            in {
                OptionChainAnalyticsIntegrationStatus.READY,
                OptionChainAnalyticsIntegrationStatus.RUNNING,
            }
            and application_ready
            and live_ready
        )
        return OptionChainAnalyticsIntegrationSnapshot(
            status=self._status,
            application_status=lifecycle_snapshot.status,
            live_option_integration_status=live_snapshot.status,
            live_option_chain_status=live_snapshot.live_option_chain_status,
            analytics_ready=self._analytics_engine.is_ready,
            running=self._status is OptionChainAnalyticsIntegrationStatus.RUNNING,
            ready=ready,
            underlying=live_snapshot.underlying,
            expiry=live_snapshot.expiry,
            source_option_chain_timestamp=(
                live_snapshot.option_chain.latest_option_chain_snapshot.timestamp
                if live_snapshot.option_chain.latest_option_chain_snapshot is not None
                else None
            ),
            latest_analytics=latest,
            analytics_history_size=len(history),
            validation_count=self._validation_count,
            start_count=self._start_count,
            stop_count=self._stop_count,
            processing_count=self._processing_count,
            analytics_update_count=self._analytics_update_count,
            duplicate_count=self._duplicate_count,
            not_ready_count=self._not_ready_count,
            last_started_at=self._last_started_at,
            last_stopped_at=self._last_stopped_at,
            last_processed_at=self._last_processed_at,
            last_outcome=self._last_outcome,
            live_option_chain_integration=live_snapshot,
            last_error=self._last_error,
        )

    def _require_running(self) -> None:
        if self._status is not OptionChainAnalyticsIntegrationStatus.RUNNING:
            raise RuntimeError("option-chain analytics integration must be RUNNING")

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock result must be datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock result must be timezone-aware")
        return value


def _is_processable(snapshot: LiveOptionChainIntegrationSnapshot) -> bool:
    return (
        snapshot.running
        and snapshot.live_option_chain_status.value == "ready"
        and snapshot.option_chain.latest_option_chain_snapshot is not None
        and snapshot.option_chain.latest_option_chain_analysis is not None
    )


def _safe_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if "{" in message or "}" in message:
        return message.split("{", 1)[0].strip()
    return message
