from __future__ import annotations

import math
from collections import deque
from dataclasses import replace
from datetime import datetime
from itertools import count
from time import monotonic, sleep

from core.base_engine import BaseEngine
from core.events import NEW_TICK, OPTION_CHAIN_UPDATED
from engines.historical_market_replay.enums import ReplayLifecycleState, ReplayMode, ReplayRecordType, ReplaySeverity
from engines.historical_market_replay.models import (
    IST,
    ReplayConfiguration,
    ReplayCounters,
    ReplayFinding,
    ReplayLatencySummary,
    ReplayManifest,
    ReplayRecord,
    ReplaySessionSnapshot,
)
from engines.historical_market_replay.report import build_report
from engines.historical_market_replay.repository import HistoricalReplayRepository


HISTORICAL_REPLAY_LOADED = "historical_replay_loaded"
HISTORICAL_REPLAY_STARTED = "historical_replay_started"
HISTORICAL_REPLAY_PAUSED = "historical_replay_paused"
HISTORICAL_REPLAY_RESUMED = "historical_replay_resumed"
HISTORICAL_REPLAY_PROGRESS_UPDATED = "historical_replay_progress_updated"
HISTORICAL_REPLAY_COMPLETED = "historical_replay_completed"
HISTORICAL_REPLAY_STOPPED = "historical_replay_stopped"
HISTORICAL_REPLAY_FAILED = "historical_replay_failed"


class ReplayLifecycleError(ValueError):
    pass


class HistoricalMarketReplayEngine(BaseEngine):
    def __init__(
        self,
        event_bus,
        configuration: ReplayConfiguration | None = None,
        *,
        clock=None,
        monotonic_clock=None,
        sleeper=None,
        repository: HistoricalReplayRepository | None = None,
        live_market_data_active=None,
    ):
        super().__init__(event_bus)
        self._configuration = configuration or ReplayConfiguration()
        if not isinstance(self._configuration, ReplayConfiguration):
            raise TypeError("configuration must be ReplayConfiguration")
        self._clock = clock or (lambda: datetime.now(IST))
        self._monotonic_clock = monotonic_clock or monotonic
        self._sleeper = sleeper or sleep
        self._repository = repository or HistoricalReplayRepository(self._configuration.output_dir)
        self._live_market_data_active = live_market_data_active or (lambda: False)
        self._counter = count(1)
        self._state = ReplayLifecycleState.IDLE
        self._manifest: ReplayManifest | None = None
        self._records: tuple[ReplayRecord, ...] = ()
        self._source_path = self._configuration.source_path
        self._cursor = 0
        self._started_at = None
        self._paused_at = None
        self._ended_at = None
        self._failure_reason = None
        self._final_summary = "-"
        self._last_report = None
        self._findings = {}
        self._finding_order = deque(maxlen=self._configuration.max_findings)
        self._recent_identities = deque(maxlen=self._configuration.max_recent_identities)
        self._latencies = deque(maxlen=self._configuration.max_latency_samples)
        self._counters = ReplayCounters()
        self._data = self.snapshot()

    @property
    def configuration(self) -> ReplayConfiguration:
        return self._configuration

    def set_live_market_data_active(self, callback) -> None:
        if not callable(callback):
            raise TypeError("live_market_data_active callback must be callable")
        self._live_market_data_active = callback

    def load_session(self, source_path=None) -> ReplaySessionSnapshot:
        self._require_state(ReplayLifecycleState.IDLE, ReplayLifecycleState.COMPLETED, ReplayLifecycleState.STOPPED, ReplayLifecycleState.FAILED)
        path = source_path or self._configuration.source_path
        if path is None:
            raise ReplayLifecycleError("historical replay source path is required")
        self._state = ReplayLifecycleState.LOADING
        self._source_path = path
        self._reset_transient(clear_loaded=True)
        try:
            self._manifest, self._records = self._repository.load_session(path)
        except Exception as exc:
            self._state = ReplayLifecycleState.FAILED
            self._failure_reason = _safe_error(exc)
            self._add_finding(ReplaySeverity.CRITICAL, "LOAD_FAILED", self._failure_reason)
            self._persist_terminal(HISTORICAL_REPLAY_FAILED)
            return self.snapshot()
        self._state = ReplayLifecycleState.READY
        self._data = self.snapshot()
        self._publish(HISTORICAL_REPLAY_LOADED, self._data)
        return self._data

    def start(self) -> ReplaySessionSnapshot:
        if not self._configuration.enabled:
            raise ReplayLifecycleError("historical replay is disabled")
        if self._configuration.mode is ReplayMode.OFF:
            raise ReplayLifecycleError("historical replay mode is OFF")
        self._require_state(ReplayLifecycleState.READY)
        self._ensure_live_inactive()
        self._state = ReplayLifecycleState.RUNNING
        self._started_at = self._started_at or self._now()
        self._paused_at = None
        self._publish(HISTORICAL_REPLAY_STARTED, self.snapshot())
        if self._configuration.mode is ReplayMode.STEP:
            self._data = self.snapshot()
            return self._data
        return self.snapshot()

    def pause(self) -> ReplaySessionSnapshot:
        self._require_state(ReplayLifecycleState.RUNNING)
        self._state = ReplayLifecycleState.PAUSED
        self._paused_at = self._now()
        self._data = self.snapshot()
        self._publish(HISTORICAL_REPLAY_PAUSED, self._data)
        return self._data

    def resume(self) -> ReplaySessionSnapshot:
        self._require_state(ReplayLifecycleState.PAUSED)
        self._state = ReplayLifecycleState.RUNNING
        self._paused_at = None
        self._publish(HISTORICAL_REPLAY_RESUMED, self.snapshot())
        self._data = self.snapshot()
        return self._data

    def step(self) -> ReplaySessionSnapshot:
        if self._configuration.mode is not ReplayMode.STEP:
            raise ReplayLifecycleError("step is valid only in STEP mode")
        if self._state is ReplayLifecycleState.READY:
            self.start()
        elif self._state is not ReplayLifecycleState.PAUSED:
            raise ReplayLifecycleError("step is valid only from READY or PAUSED")
        self._state = ReplayLifecycleState.RUNNING
        self._publish_next(apply_delay=False)
        if self._cursor >= len(self._records):
            self._complete()
        elif self._state is ReplayLifecycleState.RUNNING:
            self._state = ReplayLifecycleState.PAUSED
            self._paused_at = self._now()
        self._data = self.snapshot()
        return self._data

    def process_next(self) -> ReplaySessionSnapshot:
        if self._configuration.mode is ReplayMode.STEP:
            return self.step()
        self._require_state(ReplayLifecycleState.RUNNING)
        self._publish_next(apply_delay=True)
        if self._state is ReplayLifecycleState.RUNNING and self._cursor >= len(self._records):
            self._complete()
        self._data = self.snapshot()
        return self._data

    def process_batch(self, max_records: int | None = None) -> ReplaySessionSnapshot:
        if self._configuration.mode is ReplayMode.STEP:
            limit = 1
        else:
            limit = self._configuration.max_batch_records if max_records is None else max_records
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("max_records must be a positive integer")
        snapshot = self.snapshot()
        for _ in range(limit):
            if self._state is not ReplayLifecycleState.RUNNING:
                break
            snapshot = self.process_next()
            if snapshot.lifecycle_state is not ReplayLifecycleState.RUNNING:
                break
        return snapshot

    def drain(self) -> ReplaySessionSnapshot:
        if self._state is ReplayLifecycleState.READY:
            self.start()
        self._require_state(ReplayLifecycleState.RUNNING)
        snapshot = self.snapshot()
        while self._state is ReplayLifecycleState.RUNNING and self._cursor < len(self._records):
            snapshot = self.process_next()
        return snapshot

    def stop(self, reason: str = "Historical replay stopped.") -> ReplaySessionSnapshot:
        self._require_state(ReplayLifecycleState.RUNNING, ReplayLifecycleState.PAUSED)
        self._state = ReplayLifecycleState.STOPPED
        self._ended_at = self._now()
        self._final_summary = str(reason).strip() or "Historical replay stopped."
        self._add_finding(ReplaySeverity.INFO, "REPLAY_STOPPED", self._final_summary)
        self._persist_terminal(HISTORICAL_REPLAY_STOPPED)
        return self.snapshot()

    def reset(self, *, clear_persistent_data: bool = False) -> ReplaySessionSnapshot:
        self._state = ReplayLifecycleState.IDLE
        self._manifest = None
        self._records = ()
        self._source_path = self._configuration.source_path
        self._cursor = 0
        self._started_at = self._paused_at = self._ended_at = None
        self._failure_reason = None
        self._final_summary = "-"
        self._last_report = None
        self._reset_transient(clear_loaded=False)
        self._data = self.snapshot()
        return self._data

    def snapshot(self) -> ReplaySessionSnapshot:
        current = self._records[self._cursor] if self._cursor < len(self._records) else (self._records[-1] if self._records else None)
        findings = tuple(self._findings[key] for key in self._finding_order if key in self._findings)
        return ReplaySessionSnapshot(
            session_id=self._manifest.session_id if self._manifest else "-",
            lifecycle_state=self._state,
            mode=self._configuration.mode,
            instruments=self._manifest.instruments if self._manifest else (),
            source_path=self._source_path,
            trading_date=self._manifest.trading_date if self._manifest else None,
            total_records=len(self._records),
            current_record_index=self._cursor,
            current_sequence=getattr(current, "sequence", None),
            first_event_timestamp=self._records[0].event_timestamp if self._records else None,
            current_event_timestamp=getattr(current, "event_timestamp", None),
            last_published_event_timestamp=self._records[self._cursor - 1].event_timestamp if self._cursor > 0 else None,
            speed_multiplier=self._configuration.speed_multiplier,
            started_at=self._started_at,
            paused_at=self._paused_at,
            ended_at=self._ended_at,
            failure_reason=self._failure_reason,
            active_findings=findings,
            counters=self._counters,
            latency_summary=self._latency_summary(),
            final_outcome=getattr(self._last_report, "outcome", None),
            final_summary=self._final_summary,
        )

    def latest_report(self):
        return self._last_report

    def _publish_next(self, *, apply_delay: bool) -> None:
        if self._cursor >= len(self._records):
            return
        record = self._records[self._cursor]
        if apply_delay and self._cursor > 0:
            delay = (record.event_timestamp - self._records[self._cursor - 1].event_timestamp).total_seconds()
            if delay < 0 or not math.isfinite(delay):
                self._fail("NEGATIVE_DELAY", "Historical replay delay is invalid.")
                return
            if self._configuration.mode is ReplayMode.ACCELERATED:
                delay = delay / self._configuration.speed_multiplier
            if delay > 0:
                self._sleeper(delay)
        started = self._monotonic()
        event = NEW_TICK if record.record_type is ReplayRecordType.TICK else OPTION_CHAIN_UPDATED
        try:
            self._event_bus.publish(event, record.payload)
        except Exception as exc:
            self._fail("PUBLISH_FAILED", _safe_error(exc))
            return
        elapsed = max((self._monotonic() - started) * 1000.0, 0.0)
        self._latencies.append(elapsed)
        self._recent_identities.append((record.record_type, record.instrument, record.sequence, record.event_timestamp))
        self._cursor += 1
        self._counters = replace(
            self._counters,
            published_records=self._counters.published_records + 1,
            tick_publications=self._counters.tick_publications + (1 if record.record_type is ReplayRecordType.TICK else 0),
            option_chain_publications=self._counters.option_chain_publications + (1 if record.record_type is ReplayRecordType.OPTION_CHAIN else 0),
        )
        self._data = self.snapshot()
        self._publish(HISTORICAL_REPLAY_PROGRESS_UPDATED, self._data)

    def _complete(self) -> None:
        self._state = ReplayLifecycleState.COMPLETED
        self._ended_at = self._now()
        self._final_summary = "Historical replay completed."
        self._persist_terminal(HISTORICAL_REPLAY_COMPLETED)

    def _fail(self, code: str, message: str) -> None:
        self._state = ReplayLifecycleState.FAILED
        self._ended_at = self._now()
        self._failure_reason = message
        self._add_finding(ReplaySeverity.CRITICAL, code, message)
        self._persist_terminal(HISTORICAL_REPLAY_FAILED)

    def _persist_terminal(self, event_name: str) -> None:
        report = build_report(self.snapshot(), self._manifest, created_at=self._now())
        try:
            path = self._repository.write_report(report)
            self._counters = replace(self._counters, persistence_writes=self._counters.persistence_writes + 1)
            report = replace(report, report_path=path, snapshot=replace(report.snapshot, counters=self._counters))
        except Exception as exc:
            self._counters = replace(self._counters, persistence_failures=self._counters.persistence_failures + 1)
            self._add_finding(ReplaySeverity.ERROR, "REPORT_WRITE_FAILED", _safe_error(exc))
            report = build_report(self.snapshot(), self._manifest, created_at=self._now())
        self._last_report = report
        self._data = self.snapshot()
        self._publish(event_name, report)

    def _ensure_live_inactive(self) -> None:
        if bool(self._live_market_data_active()):
            self._add_finding(ReplaySeverity.ERROR, "LIVE_FEED_ACTIVE", "Replay cannot start while live market data is active.")
            raise ReplayLifecycleError("Replay cannot start while live market data is active.")

    def _add_finding(self, severity, code, message, observed_value=None):
        now = self._now()
        key = (code,)
        if key in self._findings:
            finding = self._findings[key].aggregate(now, str(observed_value) if observed_value is not None else None)
        else:
            finding = ReplayFinding(f"replay-{next(self._counter)}", now, severity, code, message, str(observed_value) if observed_value is not None else None)
            if len(self._finding_order) == self._finding_order.maxlen and self._finding_order:
                self._findings.pop(self._finding_order[0], None)
            self._finding_order.append(key)
        self._findings[key] = finding
        return finding

    def _reset_transient(self, *, clear_loaded: bool) -> None:
        if clear_loaded:
            self._records = ()
            self._manifest = None
            self._cursor = 0
        self._findings = {}
        self._finding_order = deque(maxlen=self._configuration.max_findings)
        self._recent_identities = deque(maxlen=self._configuration.max_recent_identities)
        self._latencies = deque(maxlen=self._configuration.max_latency_samples)
        self._counters = ReplayCounters()

    def _latency_summary(self) -> ReplayLatencySummary:
        values = tuple(self._latencies)
        if not values:
            return ReplayLatencySummary()
        return ReplayLatencySummary(len(values), values[-1], max(values), sum(values) / len(values))

    def _require_state(self, *states) -> None:
        if self._state not in states:
            allowed = ", ".join(state.value for state in states)
            raise ReplayLifecycleError(f"historical replay state must be {allowed}")

    def _publish(self, event_name: str, payload) -> None:
        self._event_bus.publish(event_name, payload)

    def _now(self):
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("historical replay clock must return timezone-aware datetime")
        return value.astimezone(IST)

    def _monotonic(self):
        value = self._monotonic_clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("historical replay monotonic clock must return a finite number")
        return float(value)


def _safe_error(exc) -> str:
    text = str(exc).strip()
    if not text:
        return exc.__class__.__name__
    for token in ("api_key", "access_token", "api_secret", "request_token"):
        text = text.replace(token, "[redacted]")
    return text
