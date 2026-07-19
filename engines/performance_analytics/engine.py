"""
Synchronous performance analytics engine for completed paper trades.
"""

from dataclasses import replace
from datetime import date, datetime, timezone

from core.event_bus import EventBus
from core.events import PAPER_TRADE_RECORDED
from engines.paper_trading.models import PaperTradeRecord
from engines.performance_analytics.calculator import PerformanceAnalyticsCalculator, post_trade_review, replay_metadata
from engines.performance_analytics.configuration import PerformanceAnalyticsConfiguration
from engines.performance_analytics.enums import AnalyticsRecordStatus
from engines.performance_analytics.events import PERFORMANCE_ANALYTICS_UPDATED, PERFORMANCE_EXPORT_COMPLETED, PERFORMANCE_EXPORT_FAILED, PERFORMANCE_TRADE_ACCEPTED
from engines.performance_analytics.exporters import PerformanceAnalyticsExporter
from engines.performance_analytics.models import AnalyticsDiagnostics, AnalyticsSnapshot, ExportResult, PostTradeReview, TradeReplayMetadata
from engines.performance_analytics.repository import PaperTradeJournalRepository


class PerformanceAnalyticsEngine:
    def __init__(
        self,
        *,
        configuration: PerformanceAnalyticsConfiguration | None = None,
        repository: PaperTradeJournalRepository | None = None,
        calculator: PerformanceAnalyticsCalculator | None = None,
        exporter: PerformanceAnalyticsExporter | None = None,
        event_bus: EventBus | None = None,
        clock=None,
    ):
        self._configuration = configuration or PerformanceAnalyticsConfiguration()
        self._event_bus = event_bus or EventBus()
        self._repository = repository or PaperTradeJournalRepository(path=self._configuration.journal_path, persistence_enabled=self._configuration.persistence_enabled)
        self._calculator = calculator or PerformanceAnalyticsCalculator()
        self._exporter = exporter or PerformanceAnalyticsExporter()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._accepted = 0
        self._duplicates = 0
        self._conflicts = 0
        self._export_failures = 0
        self._csv_exports = 0
        self._excel_exports = 0
        self._recalculations = 0
        self._last_event = "-"
        self._last_error = None
        self._loaded = 0
        self._event_bus.subscribe(PAPER_TRADE_RECORDED, self._on_paper_trade_recorded)
        if self._configuration.enabled:
            self._repository.load()
            self._loaded = len(self._repository.records())
        self._snapshot = self._calculate()

    def record_trade(self, record: PaperTradeRecord) -> AnalyticsSnapshot:
        if not self._configuration.enabled:
            self._last_event = AnalyticsRecordStatus.DISABLED.value
            return self.snapshot()
        result = self._repository.add(record)
        if result.status is AnalyticsRecordStatus.ACCEPTED:
            self._accepted += 1
            self._last_event = PERFORMANCE_TRADE_ACCEPTED
            self._safe_publish(PERFORMANCE_TRADE_ACCEPTED, record)
            self._snapshot = self._calculate()
            self._safe_publish(PERFORMANCE_ANALYTICS_UPDATED, self._snapshot)
        elif result.status is AnalyticsRecordStatus.DUPLICATE:
            self._duplicates += 1
            self._last_event = result.status.value
            self._snapshot = replace(self._snapshot, diagnostics=self._diagnostics())
        elif result.status is AnalyticsRecordStatus.CONFLICT:
            self._conflicts += 1
            self._last_error = result.message
            self._last_event = result.status.value
            self._snapshot = replace(self._snapshot, diagnostics=self._diagnostics())
        return self._snapshot

    def snapshot(self, *, instrument: str | None = None, start_date: date | None = None, end_date: date | None = None) -> AnalyticsSnapshot:
        if instrument is None and start_date is None and end_date is None:
            return self._snapshot
        return self._calculator.calculate(
            self._repository.records(),
            self._configuration,
            instrument=instrument,
            start_date=start_date,
            end_date=end_date,
            generated_at=self._now(),
            diagnostics=self._diagnostics(),
        )

    def records(self, *, instrument: str | None = None, start_date: date | None = None, end_date: date | None = None) -> tuple[PaperTradeRecord, ...]:
        return self._repository.records(instrument=instrument, start_date=start_date, end_date=end_date)

    def post_trade_review(self, trade_id: str) -> PostTradeReview:
        return post_trade_review(self._repository.get(trade_id))

    def replay_metadata(self, trade_id: str) -> TradeReplayMetadata:
        return replay_metadata(self._repository.get(trade_id))

    def export_csv(self, path=None, *, instrument: str | None = None, overwrite: bool = False) -> ExportResult:
        target = path or (self._configuration.export_directory / "performance_trades.csv")
        try:
            result = self._exporter.export_csv(self.records(instrument=instrument), target, exported_at=self._now(), overwrite=overwrite)
            self._csv_exports += 1
            self._safe_publish(PERFORMANCE_EXPORT_COMPLETED, result)
            return result
        except Exception as exc:
            self._export_failures += 1
            self._last_error = _safe_error(exc)
            self._safe_publish(PERFORMANCE_EXPORT_FAILED, self._last_error)
            raise

    def export_excel(self, path=None, *, instrument: str | None = None, overwrite: bool = False) -> ExportResult:
        target = path or (self._configuration.export_directory / "performance_analytics.xlsx")
        try:
            snap = self.snapshot(instrument=instrument)
            result = self._exporter.export_excel(self.records(instrument=instrument), snap, target, exported_at=self._now(), overwrite=overwrite)
            self._excel_exports += 1
            self._safe_publish(PERFORMANCE_EXPORT_COMPLETED, result)
            return result
        except Exception as exc:
            self._export_failures += 1
            self._last_error = _safe_error(exc)
            self._safe_publish(PERFORMANCE_EXPORT_FAILED, self._last_error)
            raise

    def reset(self, *, clear_persistent_data: bool = False) -> None:
        self._repository.reset(clear_persistent_data=clear_persistent_data)
        self._accepted = self._duplicates = self._conflicts = 0
        self._last_event = "-"
        self._last_error = None
        self._snapshot = self._calculate()

    def _on_paper_trade_recorded(self, payload) -> None:
        if isinstance(payload, PaperTradeRecord):
            self.record_trade(payload)

    def _calculate(self) -> AnalyticsSnapshot:
        self._recalculations += 1
        return self._calculator.calculate(
            self._repository.records(),
            self._configuration,
            generated_at=self._now(),
            diagnostics=self._diagnostics(),
        )

    def _diagnostics(self) -> AnalyticsDiagnostics:
        repo = self._repository.diagnostics
        return replace(
            repo,
            enabled=self._configuration.enabled,
            loaded_records=self._loaded or repo.loaded_records,
            accepted_records=self._accepted,
            duplicate_records_ignored=self._duplicates,
            conflicting_records=self._conflicts,
            csv_exports=self._csv_exports,
            excel_exports=self._excel_exports,
            export_failures=self._export_failures,
            analytics_recalculations=self._recalculations,
            last_event=self._last_event,
            last_error=self._last_error,
            broker_order_calls=0,
        )

    def _safe_publish(self, event_name: str, payload) -> None:
        try:
            self._event_bus.publish(event_name, payload)
        except Exception as exc:
            self._last_error = exc.__class__.__name__

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
        return value


def _safe_error(exc: Exception) -> str:
    return (str(exc) or exc.__class__.__name__).replace("token", "[redacted]").replace("credential", "[redacted]")
