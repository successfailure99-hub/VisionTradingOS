"""
Trade Journal & Performance Analytics V1 engine.
"""

from datetime import datetime, timezone
from threading import RLock

from application.trade_lifecycle_v1.models import TradeLifecycleV1Snapshot
from core.base_engine import BaseEngine
from core.event_bus import EventBus
from core.events import (
    TRADE_JOURNAL_DUPLICATE_SUPPRESSED,
    TRADE_JOURNAL_ENTRY_RECORDED,
    TRADE_JOURNAL_V1_UPDATED,
    TRADE_PERFORMANCE_ANALYTICS_UPDATED,
)
from engines.trade_journal_v1.analytics import TradePerformanceAnalyticsCalculator
from engines.trade_journal_v1.builder import TradeJournalEntryBuilder
from engines.trade_journal_v1.configuration import TradeJournalV1Configuration
from engines.trade_journal_v1.enums import JournalChange, TradeJournalStatus, TradeRecordStatus
from engines.option_paper_execution.models import OptionPaperPositionSnapshot
from engines.trade_journal_v1.models import (
    ActivePaperPositionCheckpoint,
    PaperRecoverySnapshot,
    TradeJournalRecordResult,
    TradeJournalV1Snapshot,
    VisionTradeJournalRecord,
)
from engines.trade_journal_v1.persistence import (
    TradeJournalPersistence,
    TradeJournalQuery,
    checkpoint_from_runtime_position,
    record_from_entry,
)
from engines.trade_journal_v1.registry import TradeJournalRegistry


class TradeJournalV1Engine(BaseEngine):
    def __init__(
        self,
        *,
        configuration: TradeJournalV1Configuration | None = None,
        builder: TradeJournalEntryBuilder | None = None,
        registry: TradeJournalRegistry | None = None,
        analytics: TradePerformanceAnalyticsCalculator | None = None,
        event_bus: EventBus | None = None,
        clock=None,
    ):
        super().__init__(event_bus or EventBus())
        self._configuration = configuration or TradeJournalV1Configuration()
        self._builder = builder or TradeJournalEntryBuilder(self._configuration)
        self._registry = registry or TradeJournalRegistry(self._configuration)
        self._persistence = TradeJournalPersistence(
            journal_path=self._configuration.journal_path,
            checkpoint_path=self._configuration.checkpoint_path,
            enabled=self._configuration.persistence_enabled,
        )
        self._analytics = analytics or TradePerformanceAnalyticsCalculator()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._status = TradeJournalStatus.CREATED
        self._change = JournalChange.INITIAL
        self._duplicate_count = 0
        self._rejected_count = 0
        self._latest_entry = None
        self._last_error = None
        self._analytics_snapshot = self._calculate_analytics()
        self._data = self.snapshot()

    def start(self) -> TradeJournalV1Snapshot:
        with self._lock:
            if self._status is TradeJournalStatus.RUNNING:
                return self.snapshot()
            self._status = TradeJournalStatus.RUNNING
            self._change = JournalChange.UNCHANGED
            self._last_error = None
            snapshot = self._store_snapshot()
        self._event_bus.publish(TRADE_JOURNAL_V1_UPDATED, snapshot)
        return snapshot

    def stop(self) -> TradeJournalV1Snapshot:
        with self._lock:
            if self._status is TradeJournalStatus.STOPPED:
                return self.snapshot()
            self._status = TradeJournalStatus.STOPPED
            self._change = JournalChange.UNCHANGED
            snapshot = self._store_snapshot()
        self._event_bus.publish(TRADE_JOURNAL_V1_UPDATED, snapshot)
        return snapshot

    def record(self, lifecycle: TradeLifecycleV1Snapshot) -> TradeJournalRecordResult:
        if not isinstance(lifecycle, TradeLifecycleV1Snapshot):
            raise TypeError("lifecycle must be TradeLifecycleV1Snapshot")
        return self._record_entry(self._builder.build(lifecycle))

    def record_option_paper_position(self, position: OptionPaperPositionSnapshot) -> TradeJournalRecordResult:
        if not isinstance(position, OptionPaperPositionSnapshot):
            raise TypeError("position must be OptionPaperPositionSnapshot")
        return self._record_entry(self._builder.build_option_paper(position))

    def _record_entry(self, entry) -> TradeJournalRecordResult:
        with self._lock:
            if self._status is not TradeJournalStatus.RUNNING:
                raise RuntimeError("trade journal engine must be RUNNING")
            try:
                result = self._registry.add(entry)
                if result.status is TradeRecordStatus.RECORDED:
                    self._latest_entry = result.entry
                    self._analytics_snapshot = self._calculate_analytics()
                    self._change = JournalChange.TRADE_RECORDED
                    self._last_error = None
                    snapshot = self._store_snapshot()
                    if getattr(result.entry, "record_state", "closed") == "closed":
                        self._persist_completed_record(result.entry)
                    self._event_bus.publish(TRADE_JOURNAL_ENTRY_RECORDED, result.entry)
                    self._event_bus.publish(TRADE_PERFORMANCE_ANALYTICS_UPDATED, self._analytics_snapshot)
                    self._event_bus.publish(TRADE_JOURNAL_V1_UPDATED, snapshot)
                elif result.status is TradeRecordStatus.DUPLICATE:
                    self._duplicate_count += 1
                    self._change = JournalChange.DUPLICATE_SUPPRESSED
                    self._store_snapshot()
                    self._event_bus.publish(TRADE_JOURNAL_DUPLICATE_SUPPRESSED, result.entry)
                else:
                    self._rejected_count += 1
                    self._last_error = result.message
                    self._store_snapshot()
                return result
            except Exception as exc:
                self._status = TradeJournalStatus.ERROR
                self._rejected_count += 1
                self._last_error = _safe_error(exc)
                self._store_snapshot()
                raise

    def snapshot(self) -> TradeJournalV1Snapshot:
        return TradeJournalV1Snapshot(
            timestamp=self._now(),
            status=self._status,
            change=self._change,
            trade_count=len(self._registry.entries()),
            duplicate_count=self._duplicate_count,
            rejected_count=self._rejected_count,
            latest_entry=self._latest_entry,
            analytics=self._analytics_snapshot,
            running=self._status is TradeJournalStatus.RUNNING,
            ready=self._status in {TradeJournalStatus.CREATED, TradeJournalStatus.RUNNING, TradeJournalStatus.STOPPED},
            last_error=self._last_error,
        )

    def entries(self):
        return self._registry.entries()

    def durable_records(self, **filters) -> tuple[VisionTradeJournalRecord, ...]:
        return self._persistence.records(TradeJournalQuery(**filters))

    def get_durable_record(self, trade_id: str) -> VisionTradeJournalRecord | None:
        return self._persistence.get_record(trade_id)

    def save_checkpoint(self, runtime_paper_position, *, trading_date, exchange: str = "NSE", timeframe: str = "1m") -> ActivePaperPositionCheckpoint | None:
        if runtime_paper_position is None:
            return None
        checkpoint = checkpoint_from_runtime_position(
            runtime_paper_position,
            trading_date=trading_date,
            exchange=exchange,
            timeframe=timeframe,
            created_at=self._now(),
        )
        self._persistence.save_checkpoint(checkpoint)
        return checkpoint

    def load_checkpoint(self, *, expected_instrument=None, trading_date=None) -> PaperRecoverySnapshot:
        return self._persistence.load_checkpoint(now=self._now(), expected_instrument=expected_instrument, trading_date=trading_date)

    def clear_checkpoint(self) -> None:
        self._persistence.clear_checkpoint()

    @property
    def persistence_write_count(self) -> int:
        return self._persistence.write_count

    @property
    def checkpoint_exists(self) -> bool:
        path = self._persistence.checkpoint_path
        return bool(path is not None and path.exists())

    def analytics_snapshot(self):
        return self._analytics_snapshot

    def clear(self) -> TradeJournalV1Snapshot:
        with self._lock:
            if self._status is not TradeJournalStatus.STOPPED:
                raise RuntimeError("trade journal engine must be stopped before clear")
            self._registry.clear()
            self._duplicate_count = 0
            self._rejected_count = 0
            self._latest_entry = None
            self._last_error = None
            self._change = JournalChange.CLEARED
            self._status = TradeJournalStatus.CLEARED
            self._analytics_snapshot = self._calculate_analytics()
            snapshot = self._store_snapshot()
        self._event_bus.publish(TRADE_JOURNAL_V1_UPDATED, snapshot)
        return snapshot

    def _persist_completed_record(self, entry) -> None:
        record = record_from_entry(
            entry,
            exchange=getattr(self._configuration, "exchange", "NSE"),
            timeframe=getattr(self._configuration, "timeframe", "1m"),
            created_at=self._now(),
        )
        self._persistence.append_record(record)

    def _calculate_analytics(self):
        return self._analytics.calculate(
            self._registry.entries(),
            self._configuration,
            timestamp=self._now(),
        )

    def _store_snapshot(self):
        snapshot = self.snapshot()
        self._data = snapshot
        return snapshot

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
        return value


def _safe_error(exc: Exception) -> str:
    return str(exc).replace("token", "[redacted]").replace("credential", "[redacted]")
