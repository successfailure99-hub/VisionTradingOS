"""
Zerodha historical data manager.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from threading import RLock

from brokers.zerodha.historical.client import ZerodhaHistoricalClientProtocol
from brokers.zerodha.historical.enums import ZerodhaHistoricalStatus
from brokers.zerodha.historical.intervals import to_zerodha_interval
from brokers.zerodha.historical.models import ZerodhaHistoricalRequest, ZerodhaHistoricalResult, ZerodhaHistoricalSnapshot
from brokers.zerodha.historical.normalizer import ZerodhaHistoricalCandleNormalizer
from brokers.zerodha.historical.planner import ZerodhaHistoricalRequestPlanner
from brokers.zerodha.historical.validator import ZerodhaHistoricalSeriesValidator
from brokers.zerodha.instruments import ZerodhaInstrumentResolution
from core.enums.timeframe import TimeFrame


def _default_clock() -> datetime:
    return datetime.now(UTC)


class ZerodhaHistoricalDataManager:
    def __init__(
        self,
        *,
        client: ZerodhaHistoricalClientProtocol,
        normalizer: ZerodhaHistoricalCandleNormalizer | None = None,
        planner: ZerodhaHistoricalRequestPlanner | None = None,
        validator: ZerodhaHistoricalSeriesValidator | None = None,
        clock=None,
    ):
        if not hasattr(client, "historical_data") or not callable(client.historical_data):
            raise TypeError("client must expose historical_data")
        self._client = client
        self._normalizer = normalizer or ZerodhaHistoricalCandleNormalizer()
        self._planner = planner or ZerodhaHistoricalRequestPlanner()
        self._validator = validator or ZerodhaHistoricalSeriesValidator()
        self._clock = clock or _default_clock
        self._lock = RLock()
        self._status = ZerodhaHistoricalStatus.CREATED
        self._fetch_count = 0
        self._successful_fetch_count = 0
        self._failed_fetch_count = 0
        self._total_source_records = 0
        self._total_normalized_candles = 0
        self._last_request: ZerodhaHistoricalRequest | None = None
        self._last_result: ZerodhaHistoricalResult | None = None
        self._last_started_at: datetime | None = None
        self._last_completed_at: datetime | None = None
        self._last_error: str | None = None

    def fetch(
        self,
        request: ZerodhaHistoricalRequest,
    ) -> ZerodhaHistoricalResult:
        if not isinstance(request, ZerodhaHistoricalRequest):
            raise TypeError("request must be ZerodhaHistoricalRequest")
        with self._lock:
            self._status = ZerodhaHistoricalStatus.FETCHING
            self._fetch_count += 1
            self._last_request = request
            try:
                self._last_started_at = self._now()
                result = self._fetch_unlocked(request)
            except Exception as exc:
                self._status = ZerodhaHistoricalStatus.ERROR
                self._failed_fetch_count += 1
                self._last_error = _safe_error(exc)
                raise
            self._status = ZerodhaHistoricalStatus.READY if result.candles else ZerodhaHistoricalStatus.EMPTY
            self._successful_fetch_count += 1
            self._total_source_records += result.source_record_count
            self._total_normalized_candles += result.normalized_count
            self._last_completed_at = result.fetched_at
            self._last_result = result
            self._last_error = None
            return result

    def fetch_resolution(
        self,
        resolution: ZerodhaInstrumentResolution,
        *,
        timeframe: TimeFrame,
        start_at: datetime,
        end_at: datetime,
    ) -> ZerodhaHistoricalResult:
        if not isinstance(resolution, ZerodhaInstrumentResolution):
            raise TypeError("resolution must be ZerodhaInstrumentResolution")
        request = ZerodhaHistoricalRequest(
            instrument_token=resolution.subscription.instrument_token,
            instrument=resolution.instrument,
            exchange=resolution.subscription.exchange,
            timeframe=timeframe,
            start_at=start_at,
            end_at=end_at,
            continuous=False,
            include_open_interest=False,
        )
        return self.fetch(request)

    def snapshot(self) -> ZerodhaHistoricalSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def clear(self) -> ZerodhaHistoricalSnapshot:
        with self._lock:
            self._status = ZerodhaHistoricalStatus.CLEARED
            self._fetch_count = 0
            self._successful_fetch_count = 0
            self._failed_fetch_count = 0
            self._total_source_records = 0
            self._total_normalized_candles = 0
            self._last_request = None
            self._last_result = None
            self._last_started_at = None
            self._last_completed_at = None
            self._last_error = None
            return self._snapshot_unlocked()

    def _fetch_unlocked(self, request: ZerodhaHistoricalRequest) -> ZerodhaHistoricalResult:
        chunks = self._planner.plan(request)
        raw_records = []
        normalized = []
        rejected = 0
        interval = to_zerodha_interval(request.timeframe)
        for chunk in chunks:
            response = self._client.historical_data(
                instrument_token=request.instrument_token,
                from_date=chunk.start_at,
                to_date=chunk.end_at,
                interval=interval,
                continuous=request.continuous,
                oi=request.include_open_interest,
            )
            if isinstance(response, (str, bytes, Mapping)) or not isinstance(response, Sequence):
                raise TypeError("historical_data response must be a sequence of mappings")
            for raw in response:
                raw_records.append(raw)
                try:
                    normalized.append(self._normalizer.normalize(raw, instrument=request.instrument, timeframe=request.timeframe))
                except Exception:
                    rejected += 1
                    continue
        candles, gaps, duplicate_count = self._validator.validate(normalized, timeframe=request.timeframe)
        fetched_at = self._now()
        return ZerodhaHistoricalResult(
            request=request,
            candles=candles,
            gaps=gaps,
            source_record_count=len(raw_records),
            normalized_count=len(candles),
            duplicate_count=duplicate_count,
            rejected_count=rejected,
            first_candle_at=candles[0].start_time if candles else None,
            last_candle_at=candles[-1].start_time if candles else None,
            fetched_at=fetched_at,
        )

    def _snapshot_unlocked(self) -> ZerodhaHistoricalSnapshot:
        return ZerodhaHistoricalSnapshot(
            status=self._status,
            fetch_count=self._fetch_count,
            successful_fetch_count=self._successful_fetch_count,
            failed_fetch_count=self._failed_fetch_count,
            total_source_records=self._total_source_records,
            total_normalized_candles=self._total_normalized_candles,
            last_request=self._last_request,
            last_result=self._last_result,
            last_started_at=self._last_started_at,
            last_completed_at=self._last_completed_at,
            last_error=self._last_error,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock result must be datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock result must be timezone-aware")
        return value


def _safe_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if "{" in message or "}" in message:
        return message.split("{", 1)[0].strip()
    return message
