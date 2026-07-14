"""
Immutable option-chain analytics integration models.
"""

from dataclasses import dataclass
from datetime import date, datetime

from application.enums import RuntimeStatus
from application.live_option_chain import LiveOptionChainStatus
from application.live_option_chain_integration import (
    LiveOptionChainIntegrationSnapshot,
    LiveOptionChainIntegrationStatus,
)
from application.option_chain_analytics_integration.enums import (
    OptionChainAnalyticsIntegrationStatus,
    OptionChainAnalyticsProcessingResult,
)
from core.enums.instrument import Instrument
from engines.option_chain_analytics import OptionChainAnalyticsSnapshot


def _non_negative(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be non-negative integer")
    return value


def _aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class OptionChainAnalyticsProcessingOutcome:
    result: OptionChainAnalyticsProcessingResult
    processed: bool
    analytics_updated: bool
    source_timestamp: datetime | None
    analytics_snapshot: OptionChainAnalyticsSnapshot | None
    completed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.result, OptionChainAnalyticsProcessingResult):
            raise TypeError("result must be OptionChainAnalyticsProcessingResult")
        if type(self.processed) is not bool or type(self.analytics_updated) is not bool:
            raise TypeError("processed and analytics_updated must be bool")
        _aware(self.source_timestamp, "source_timestamp")
        _aware(self.completed_at, "completed_at")
        if self.analytics_snapshot is not None and not isinstance(
            self.analytics_snapshot,
            OptionChainAnalyticsSnapshot,
        ):
            raise TypeError("analytics_snapshot must be OptionChainAnalyticsSnapshot or None")
        if self.processed and (self.source_timestamp is None or self.analytics_snapshot is None):
            raise ValueError("processed outcome requires source timestamp and analytics snapshot")
        if self.analytics_updated and not self.processed:
            raise ValueError("analytics_updated requires processed")
        if self.result is OptionChainAnalyticsProcessingResult.NOT_READY:
            if self.processed or self.analytics_snapshot is not None:
                raise ValueError("NOT_READY outcome must not contain analytics output")


@dataclass(frozen=True, slots=True)
class OptionChainAnalyticsIntegrationSnapshot:
    status: OptionChainAnalyticsIntegrationStatus
    application_status: RuntimeStatus
    live_option_integration_status: LiveOptionChainIntegrationStatus
    live_option_chain_status: LiveOptionChainStatus
    analytics_ready: bool
    running: bool
    ready: bool
    underlying: Instrument
    expiry: date
    source_option_chain_timestamp: datetime | None
    latest_analytics: OptionChainAnalyticsSnapshot | None
    analytics_history_size: int
    validation_count: int
    start_count: int
    stop_count: int
    processing_count: int
    analytics_update_count: int
    duplicate_count: int
    not_ready_count: int
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    last_processed_at: datetime | None
    last_outcome: OptionChainAnalyticsProcessingOutcome | None
    live_option_chain_integration: LiveOptionChainIntegrationSnapshot
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, OptionChainAnalyticsIntegrationStatus):
            raise TypeError("status must be OptionChainAnalyticsIntegrationStatus")
        if not isinstance(self.application_status, RuntimeStatus):
            raise TypeError("application_status must be RuntimeStatus")
        if not isinstance(self.live_option_integration_status, LiveOptionChainIntegrationStatus):
            raise TypeError("live_option_integration_status must be LiveOptionChainIntegrationStatus")
        if not isinstance(self.live_option_chain_status, LiveOptionChainStatus):
            raise TypeError("live_option_chain_status must be LiveOptionChainStatus")
        if type(self.analytics_ready) is not bool or type(self.running) is not bool or type(self.ready) is not bool:
            raise TypeError("analytics_ready, running and ready must be bool")
        if self.running and self.status is not OptionChainAnalyticsIntegrationStatus.RUNNING:
            raise ValueError("running snapshot requires RUNNING status")
        if not isinstance(self.underlying, Instrument):
            raise TypeError("underlying must be Instrument")
        if not isinstance(self.expiry, date) or isinstance(self.expiry, datetime):
            raise TypeError("expiry must be date")
        _aware(self.source_option_chain_timestamp, "source_option_chain_timestamp")
        if self.latest_analytics is not None and not isinstance(
            self.latest_analytics,
            OptionChainAnalyticsSnapshot,
        ):
            raise TypeError("latest_analytics must be OptionChainAnalyticsSnapshot or None")
        for name in (
            "analytics_history_size",
            "validation_count",
            "start_count",
            "stop_count",
            "processing_count",
            "analytics_update_count",
            "duplicate_count",
            "not_ready_count",
        ):
            _non_negative(getattr(self, name), name)
        _aware(self.last_started_at, "last_started_at")
        _aware(self.last_stopped_at, "last_stopped_at")
        _aware(self.last_processed_at, "last_processed_at")
        if self.last_outcome is not None and not isinstance(self.last_outcome, OptionChainAnalyticsProcessingOutcome):
            raise TypeError("last_outcome must be OptionChainAnalyticsProcessingOutcome or None")
        if not isinstance(self.live_option_chain_integration, LiveOptionChainIntegrationSnapshot):
            raise TypeError("live_option_chain_integration must be LiveOptionChainIntegrationSnapshot")
        if self.last_error is not None and not isinstance(self.last_error, str):
            raise TypeError("last_error must be str or None")
