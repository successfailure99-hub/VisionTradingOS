"""
Historical warm-up and explicit backfill coordinator.
"""

from datetime import UTC, datetime
from threading import RLock

from application.enums import RuntimeStatus
from application.historical_warmup.configuration import HistoricalWarmupConfiguration
from application.historical_warmup.daily_ohlc import derive_daily_ohlc
from application.historical_warmup.enums import HistoricalWarmupOperation, HistoricalWarmupStatus
from application.historical_warmup.models import (
    HistoricalSeedResult,
    HistoricalWarmupInstrumentResult,
    HistoricalWarmupSnapshot,
)
from application.lifecycle_manager import ApplicationLifecycleManager
from application.models import RuntimeSnapshot
from brokers.zerodha.historical import (
    HistoricalGapType,
    ZerodhaHistoricalDataManager,
    ZerodhaHistoricalRequest,
    ZerodhaHistoricalResult,
)
from brokers.zerodha.instruments import ZerodhaInstrumentResolution
from core.enums.instrument import Instrument
from core.models.candle import Candle


def _default_clock() -> datetime:
    return datetime.now(UTC)


class HistoricalWarmupCoordinator:
    def __init__(
        self,
        *,
        lifecycle: ApplicationLifecycleManager,
        historical_manager: ZerodhaHistoricalDataManager,
        resolutions: tuple[ZerodhaInstrumentResolution, ...],
        configuration: HistoricalWarmupConfiguration | None = None,
        clock=None,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be ApplicationLifecycleManager")
        if not isinstance(historical_manager, ZerodhaHistoricalDataManager):
            raise TypeError("historical_manager must be ZerodhaHistoricalDataManager")
        resolutions = tuple(resolutions)
        if not resolutions:
            raise ValueError("at least one resolution is required")
        if any(not isinstance(resolution, ZerodhaInstrumentResolution) for resolution in resolutions):
            raise TypeError("resolutions must contain ZerodhaInstrumentResolution values")
        instruments = [resolution.instrument for resolution in resolutions]
        tokens = [resolution.subscription.instrument_token for resolution in resolutions]
        if len(set(instruments)) != len(instruments):
            raise ValueError("duplicate resolution instrument")
        if len(set(tokens)) != len(tokens):
            raise ValueError("duplicate resolution token")
        if configuration is None:
            configuration = HistoricalWarmupConfiguration()
        if not isinstance(configuration, HistoricalWarmupConfiguration):
            raise TypeError("configuration must be HistoricalWarmupConfiguration")

        self._lifecycle = lifecycle
        self._historical_manager = historical_manager
        self._resolutions = resolutions
        self._configuration = configuration
        self._clock = clock or _default_clock
        self._lock = RLock()
        self._status = HistoricalWarmupStatus.CREATED
        self._operation: HistoricalWarmupOperation | None = None
        self._results: tuple[HistoricalWarmupInstrumentResult, ...] = ()
        self._operation_count = 0
        self._successful_operation_count = 0
        self._failed_operation_count = 0
        self._total_fetched_candles = 0
        self._total_seeded_candles = 0
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._last_error: str | None = None

    def warm_up(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        previous_day_start_at: datetime | None = None,
        previous_day_end_at: datetime | None = None,
    ) -> HistoricalWarmupSnapshot:
        with self._lock:
            try:
                self._begin_operation(HistoricalWarmupOperation.WARMUP)
                self._require_running()
                self._validate_range(start_at, end_at)
                if (previous_day_start_at is None) != (previous_day_end_at is None):
                    raise ValueError("previous-day bounds must be supplied together")
                if previous_day_start_at is not None:
                    self._validate_range(previous_day_start_at, previous_day_end_at)
                results = []
                self._status = HistoricalWarmupStatus.FETCHING
                for resolution in self._resolutions:
                    results.append(
                        self._warm_up_resolution(
                            resolution,
                            start_at=start_at,
                            end_at=end_at,
                            previous_day_start_at=previous_day_start_at,
                            previous_day_end_at=previous_day_end_at,
                        )
                    )
                self._finish_with_results(tuple(results))
                return self._snapshot_unlocked()
            except Exception as exc:
                self._record_operation_error(exc)
                raise

    def backfill(
        self,
        *,
        instrument: Instrument,
        end_at: datetime,
    ) -> HistoricalWarmupSnapshot:
        with self._lock:
            try:
                self._begin_operation(HistoricalWarmupOperation.BACKFILL)
                self._require_running()
                if not isinstance(instrument, Instrument):
                    raise TypeError("instrument must be Instrument")
                self._validate_aware(end_at, "end_at")
                resolution = self._resolution_for(instrument)
                history = self._lifecycle.orchestrator.get_candle_history(instrument.value)
                if not history:
                    raise ValueError("No closed candle history exists; call warm_up() before backfill.")
                start_at = history[-1].end_time
                if end_at < start_at:
                    raise ValueError("end_at must be later than the latest closed candle")
                if end_at == start_at:
                    result = self._empty_result(resolution, history[-1].start_time, end_at)
                    snapshot = self._lifecycle.orchestrator.get_runtime(instrument.value).snapshot()
                    instrument_result = self._make_instrument_result(
                        instrument=instrument,
                        historical_result=result,
                        requested_candles=(),
                        accepted=(),
                        runtime_snapshot=snapshot,
                        daily_ohlc=None,
                        error=None,
                    )
                    self._finish_with_results((instrument_result,))
                    return self._snapshot_unlocked()
                self._status = HistoricalWarmupStatus.FETCHING
                result = self._historical_manager.fetch_resolution(
                    resolution,
                    timeframe=self._configuration.timeframe,
                    start_at=start_at,
                    end_at=end_at,
                )
                existing_starts = {candle.start_time for candle in history}
                eligible = tuple(
                    candle
                    for candle in result.candles
                    if candle.start_time not in existing_starts
                    and candle.start_time < end_at
                    and candle.end_time <= end_at
                )
                self._status = HistoricalWarmupStatus.APPLYING
                accepted, snapshot = self._lifecycle.orchestrator.warm_up_candles(instrument.value, eligible)
                instrument_result = self._make_instrument_result(
                    instrument=instrument,
                    historical_result=result,
                    requested_candles=eligible,
                    accepted=accepted,
                    runtime_snapshot=snapshot,
                    daily_ohlc=None,
                    error=None,
                )
                self._finish_with_results((instrument_result,))
                return self._snapshot_unlocked()
            except Exception as exc:
                self._record_operation_error(exc)
                raise

    def snapshot(self) -> HistoricalWarmupSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def clear(self) -> HistoricalWarmupSnapshot:
        with self._lock:
            self._status = HistoricalWarmupStatus.CLEARED
            self._operation = None
            self._results = ()
            self._operation_count = 0
            self._successful_operation_count = 0
            self._failed_operation_count = 0
            self._total_fetched_candles = 0
            self._total_seeded_candles = 0
            self._started_at = None
            self._completed_at = None
            self._last_error = None
            return self._snapshot_unlocked()

    def _warm_up_resolution(
        self,
        resolution: ZerodhaInstrumentResolution,
        *,
        start_at: datetime,
        end_at: datetime,
        previous_day_start_at: datetime | None,
        previous_day_end_at: datetime | None,
    ) -> HistoricalWarmupInstrumentResult:
        instrument = resolution.instrument
        try:
            self._lifecycle.orchestrator.get_runtime(instrument.value)
            daily_ohlc = None
            if previous_day_start_at is not None and previous_day_end_at is not None:
                previous = self._historical_manager.fetch_resolution(
                    resolution,
                    timeframe=self._configuration.timeframe,
                    start_at=previous_day_start_at,
                    end_at=previous_day_end_at,
                )
                if previous.candles:
                    daily_ohlc = derive_daily_ohlc(previous.candles, instrument=instrument)
                    self._lifecycle.orchestrator.process_daily_ohlc(instrument.value, daily_ohlc)
            result = self._historical_manager.fetch_resolution(
                resolution,
                timeframe=self._configuration.timeframe,
                start_at=start_at,
                end_at=end_at,
            )
            if self._configuration.strict_gap_validation and self._missing_gap_count(result) > 0:
                raise ValueError("missing historical candle interval")

            self._status = HistoricalWarmupStatus.APPLYING
            accepted, runtime_snapshot = self._lifecycle.orchestrator.warm_up_candles(
                instrument.value,
                result.candles,
            )
            return self._make_instrument_result(
                instrument=instrument,
                historical_result=result,
                requested_candles=result.candles,
                accepted=accepted,
                runtime_snapshot=runtime_snapshot,
                daily_ohlc=daily_ohlc,
                error=None,
            )
        except Exception as exc:
            error = _safe_error(exc)
            empty = self._empty_result(resolution, start_at, end_at)
            snapshot = self._safe_runtime_snapshot(instrument)
            return self._make_instrument_result(
                instrument=instrument,
                historical_result=empty,
                requested_candles=(),
                accepted=(),
                runtime_snapshot=snapshot,
                daily_ohlc=None,
                error=error,
            )

    def _make_instrument_result(
        self,
        *,
        instrument: Instrument,
        historical_result: ZerodhaHistoricalResult,
        requested_candles: tuple[Candle, ...],
        accepted: tuple[Candle, ...],
        runtime_snapshot: RuntimeSnapshot,
        daily_ohlc,
        error: str | None,
    ) -> HistoricalWarmupInstrumentResult:
        requested = len(requested_candles)
        accepted_count = len(accepted)
        duplicate_count = max(0, requested - accepted_count)
        seed_result = HistoricalSeedResult(
            instrument=instrument,
            requested_count=requested,
            accepted_count=accepted_count,
            duplicate_count=duplicate_count,
            rejected_count=0,
            first_candle_at=accepted[0].start_time if accepted else None,
            last_candle_at=accepted[-1].start_time if accepted else None,
        )
        return HistoricalWarmupInstrumentResult(
            instrument=instrument,
            historical_result=historical_result,
            seed_result=seed_result,
            daily_ohlc=daily_ohlc,
            runtime_snapshot=runtime_snapshot,
            gaps_detected=len(historical_result.gaps),
            completed=error is None,
            error=error,
        )

    def _begin_operation(self, operation: HistoricalWarmupOperation) -> None:
        self._status = HistoricalWarmupStatus.VALIDATING
        self._operation = operation
        self._operation_count += 1
        self._completed_at = None
        self._last_error = None
        started_at = self._now()
        self._started_at = started_at
        self._results = ()

    def _finish_with_results(self, results: tuple[HistoricalWarmupInstrumentResult, ...]) -> None:
        completed_at = self._now()
        completed = tuple(result.instrument for result in results if result.completed)
        failed = tuple(result.instrument for result in results if not result.completed)
        seeded = sum(result.seed_result.accepted_count for result in results)
        fetched = sum(result.historical_result.normalized_count for result in results)
        self._results = results
        self._total_fetched_candles += fetched
        self._total_seeded_candles += seeded
        if failed and completed:
            self._status = HistoricalWarmupStatus.PARTIAL
        elif failed:
            self._status = HistoricalWarmupStatus.ERROR
        elif seeded == 0:
            self._status = HistoricalWarmupStatus.EMPTY
        else:
            self._status = HistoricalWarmupStatus.READY
        if self._status is HistoricalWarmupStatus.ERROR:
            self._failed_operation_count += 1
            self._last_error = "; ".join(result.error for result in results if result.error)
        else:
            self._successful_operation_count += 1
            self._last_error = None
        self._completed_at = completed_at

    def _record_operation_error(self, exc: Exception) -> None:
        self._status = HistoricalWarmupStatus.ERROR
        self._failed_operation_count += 1
        self._last_error = _safe_error(exc)
        try:
            self._completed_at = self._now()
        except Exception:
            self._completed_at = None

    def _snapshot_unlocked(self) -> HistoricalWarmupSnapshot:
        completed = tuple(result.instrument for result in self._results if result.completed)
        failed = tuple(result.instrument for result in self._results if not result.completed)
        return HistoricalWarmupSnapshot(
            status=self._status,
            operation=self._operation,
            configured_instruments=tuple(resolution.instrument for resolution in self._resolutions),
            completed_instruments=completed,
            failed_instruments=failed,
            results=self._results,
            operation_count=self._operation_count,
            successful_operation_count=self._successful_operation_count,
            failed_operation_count=self._failed_operation_count,
            total_fetched_candles=self._total_fetched_candles,
            total_seeded_candles=self._total_seeded_candles,
            started_at=self._started_at,
            completed_at=self._completed_at,
            last_error=self._last_error,
        )

    def _resolution_for(self, instrument: Instrument) -> ZerodhaInstrumentResolution:
        for resolution in self._resolutions:
            if resolution.instrument is instrument:
                return resolution
        raise ValueError("instrument is not configured for historical warm-up")

    def _require_running(self) -> None:
        if self._lifecycle.status is not RuntimeStatus.RUNNING:
            raise RuntimeError("Historical warm-up requires RUNNING lifecycle.")
        if self._lifecycle.orchestrator.status is not RuntimeStatus.RUNNING:
            raise RuntimeError("Historical warm-up requires RUNNING orchestrator.")

    def _validate_range(self, start_at: datetime, end_at: datetime) -> None:
        self._validate_aware(start_at, "start_at")
        self._validate_aware(end_at, "end_at")
        if start_at >= end_at:
            raise ValueError("start_at must be before end_at")

    def _validate_aware(self, value: datetime, field_name: str) -> None:
        if not isinstance(value, datetime):
            raise TypeError(f"{field_name} must be datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")

    def _now(self) -> datetime:
        value = self._clock()
        self._validate_aware(value, "clock result")
        return value

    def _missing_gap_count(self, result: ZerodhaHistoricalResult) -> int:
        return sum(1 for gap in result.gaps if gap.gap_type is HistoricalGapType.MISSING_INTERVAL)

    def _empty_result(
        self,
        resolution: ZerodhaInstrumentResolution,
        start_at: datetime,
        end_at: datetime,
    ) -> ZerodhaHistoricalResult:
        request = ZerodhaHistoricalRequest(
            instrument_token=resolution.subscription.instrument_token,
            instrument=resolution.instrument,
            exchange=resolution.subscription.exchange,
            timeframe=self._configuration.timeframe,
            start_at=start_at,
            end_at=end_at,
        )
        return ZerodhaHistoricalResult(
            request=request,
            candles=(),
            gaps=(),
            source_record_count=0,
            normalized_count=0,
            duplicate_count=0,
            rejected_count=0,
            first_candle_at=None,
            last_candle_at=None,
            fetched_at=self._now(),
        )

    def _safe_runtime_snapshot(self, instrument: Instrument) -> RuntimeSnapshot:
        try:
            return self._lifecycle.orchestrator.get_runtime(instrument.value).snapshot()
        except Exception:
            snapshots = self._lifecycle.orchestrator.snapshot().runtime_snapshots
            if not snapshots:
                raise
            return snapshots[0]


def _safe_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if "{" in message or "}" in message:
        return message.split("{", 1)[0].strip()
    return message
