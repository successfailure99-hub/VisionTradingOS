from __future__ import annotations

from collections import deque
from dataclasses import replace
from datetime import datetime
from itertools import count
from pathlib import Path
from zoneinfo import ZoneInfo

from application.enums import RuntimeStatus
from core.events import (
    BACKTEST_COMPLETED,
    BACKTEST_FAILED,
    BACKTEST_PAUSED,
    BACKTEST_READY,
    BACKTEST_RESUMED,
    BACKTEST_SESSION_COMPLETED,
    BACKTEST_SESSION_FAILED,
    BACKTEST_SESSION_STARTED,
    BACKTEST_STARTED,
    BACKTEST_STOPPED,
    BACKTEST_UPDATED,
    NEW_TICK,
    OPTION_CHAIN_UPDATED,
)
from core.models.tick import Tick
from engines.deterministic_backtest.enums import (
    BacktestLifecycleState,
    BacktestMode,
    BacktestOutcome,
    BacktestSeverity,
    ReproducibilityStatus,
)
from engines.deterministic_backtest.models import (
    BacktestAggregateAnalytics,
    BacktestBatchResult,
    BacktestConfiguration,
    BacktestFinding,
    BacktestSessionProgress,
    BacktestSessionResult,
    BacktestSnapshot,
    aggregate_analytics,
    runtime_configuration_fingerprint,
    session_result_digest,
    stable_digest,
)
from engines.deterministic_backtest.report import BacktestReportRepository, with_report_path
from engines.historical_market_replay.enums import ReplayLifecycleState, ReplayMode, ReplayOutcome
from engines.option_chain.models import OptionChainSnapshot


IST = ZoneInfo("Asia/Kolkata")


class BacktestLifecycleError(ValueError):
    pass


class DeterministicBacktestEngine:
    def __init__(
        self,
        event_bus,
        *,
        configuration: BacktestConfiguration | None = None,
        orchestrator=None,
        repository: BacktestReportRepository | None = None,
        live_market_data_active=None,
        live_option_chain_active=None,
        clock=None,
    ):
        self._event_bus = event_bus
        self._configuration = configuration or BacktestConfiguration()
        if not isinstance(self._configuration, BacktestConfiguration):
            raise TypeError("configuration must be BacktestConfiguration")
        self._orchestrator = orchestrator
        self._repository = repository or BacktestReportRepository(self._configuration.output_directory)
        self._live_market_data_active = live_market_data_active or (lambda: False)
        self._live_option_chain_active = live_option_chain_active or (lambda: False)
        self._clock = clock or (lambda: datetime.now(IST))
        self._counter = count(1)
        self._state = BacktestLifecycleState.IDLE
        self._session_index = -1
        self._session_fingerprints: tuple[str, ...] = ()
        self._run_fingerprint = "-"
        self._run_id = "-"
        self._started_at = None
        self._ended_at = None
        self._findings = {}
        self._finding_order = deque(maxlen=self._configuration.max_findings)
        self._session_results: tuple[BacktestSessionResult, ...] = ()
        self._latest_result: BacktestBatchResult | None = None
        self._processing = False
        self._routing_event = False
        self._terminal_persisted = False
        self._session_event_hash = stable_digest({"events": ()})
        self._last_result_digest = "-"
        self._result_digests_by_fingerprint = {}
        self._event_bus.subscribe(NEW_TICK, self._on_tick)
        self._event_bus.subscribe(OPTION_CHAIN_UPDATED, self._on_option_chain)

    @property
    def configuration(self) -> BacktestConfiguration:
        return self._configuration

    @property
    def repository(self) -> BacktestReportRepository:
        return self._repository

    def set_live_market_data_active(self, callback) -> None:
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._live_market_data_active = callback

    def set_live_option_chain_active(self, callback) -> None:
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._live_option_chain_active = callback

    def prepare(self) -> BacktestSnapshot:
        self._require_state(BacktestLifecycleState.IDLE)
        if not self._configuration.enabled:
            return self.snapshot()
        self._ensure_orchestrator()
        self._ensure_live_inactive()
        self._session_fingerprints = tuple(self._manifest_fingerprint(path) for path in self._configuration.session_paths)
        self._run_fingerprint = runtime_configuration_fingerprint(
            self._configuration,
            self._session_fingerprints,
            getattr(self._orchestrator, "configuration", None),
        )
        self._run_id = f"backtest-{self._run_fingerprint[:12]}"
        self._state = BacktestLifecycleState.READY
        self._add_finding(BacktestSeverity.INFO, "BACKTEST_PREPARED", "Backtest prepared.")
        self._publish(BACKTEST_READY)
        return self.snapshot()

    def start(self) -> BacktestSnapshot:
        if self._state is BacktestLifecycleState.IDLE:
            self.prepare()
        self._require_state(BacktestLifecycleState.READY)
        self._ensure_live_inactive()
        self._state = BacktestLifecycleState.RUNNING
        self._started_at = self._started_at or self._now()
        self._session_index = -1
        self._session_results = ()
        self._terminal_persisted = False
        self._session_event_hash = stable_digest({"events": ()})
        self._add_finding(BacktestSeverity.INFO, "BACKTEST_STARTED", "Backtest started.")
        self._publish(BACKTEST_STARTED)
        return self.snapshot()

    def process_next(self) -> BacktestSnapshot:
        if self._processing:
            return self.snapshot()
        if self._state is not BacktestLifecycleState.RUNNING:
            return self.snapshot()
        self._processing = True
        try:
            if self._active_replay().lifecycle_state is ReplayLifecycleState.RUNNING:
                replay_snapshot = self._replay().process_batch(max_records=1)
                if replay_snapshot.lifecycle_state in {ReplayLifecycleState.COMPLETED, ReplayLifecycleState.FAILED, ReplayLifecycleState.STOPPED}:
                    self._finish_session(replay_snapshot)
                return self.snapshot()
            if self._session_index + 1 >= len(self._configuration.session_paths):
                self._complete()
                return self.snapshot()
            self._start_next_session()
            return self.snapshot()
        except Exception as exc:
            self._fail("BACKTEST_FAILED", _safe_error(exc))
            return self.snapshot()
        finally:
            self._processing = False

    def process_batch(self, max_sessions_or_records: int = 1) -> BacktestSnapshot:
        if isinstance(max_sessions_or_records, bool) or not isinstance(max_sessions_or_records, int) or max_sessions_or_records <= 0:
            raise ValueError("max_sessions_or_records must be a positive integer")
        snapshot = self.snapshot()
        for _ in range(max_sessions_or_records):
            if self._state is not BacktestLifecycleState.RUNNING:
                break
            before = (self._session_index, self._active_replay().current_record_index, self._state)
            snapshot = self.process_next()
            after = (self._session_index, self._active_replay().current_record_index, self._state)
            if after == before:
                break
        return snapshot

    def pause(self) -> BacktestSnapshot:
        self._require_state(BacktestLifecycleState.RUNNING)
        replay = self._active_replay()
        if replay.lifecycle_state is ReplayLifecycleState.RUNNING:
            self._replay().pause()
        self._state = BacktestLifecycleState.PAUSED
        self._publish(BACKTEST_PAUSED)
        return self.snapshot()

    def resume(self) -> BacktestSnapshot:
        self._require_state(BacktestLifecycleState.PAUSED)
        replay = self._active_replay()
        if replay.lifecycle_state is ReplayLifecycleState.PAUSED:
            self._replay().resume()
        self._state = BacktestLifecycleState.RUNNING
        self._publish(BACKTEST_RESUMED)
        return self.snapshot()

    def stop(self) -> BacktestSnapshot:
        self._require_state(BacktestLifecycleState.RUNNING, BacktestLifecycleState.PAUSED)
        replay = self._active_replay()
        if replay.lifecycle_state in {ReplayLifecycleState.RUNNING, ReplayLifecycleState.PAUSED}:
            replay = self._replay().stop("Backtest stopped.")
            self._finish_session(replay)
        self._state = BacktestLifecycleState.STOPPED
        self._ended_at = self._ended_at or self._now()
        self._add_finding(BacktestSeverity.WARNING, "BACKTEST_STOPPED", "Backtest stopped.")
        self._persist_terminal(BacktestOutcome.STOPPED, BACKTEST_STOPPED)
        return self.snapshot()

    def reset(self) -> BacktestSnapshot:
        self._state = BacktestLifecycleState.IDLE
        self._session_index = -1
        self._session_fingerprints = ()
        self._run_fingerprint = "-"
        self._run_id = "-"
        self._started_at = None
        self._ended_at = None
        self._findings = {}
        self._finding_order = deque(maxlen=self._configuration.max_findings)
        self._session_results = ()
        self._latest_result = None
        self._processing = False
        self._routing_event = False
        self._terminal_persisted = False
        self._session_event_hash = stable_digest({"events": ()})
        self._last_result_digest = "-"
        if self._orchestrator is not None:
            self._orchestrator.reset_backtest_run_state()
        return self.snapshot()

    def snapshot(self) -> BacktestSnapshot:
        replay = self._active_replay()
        analytics = aggregate_analytics(
            tuple(result.analytics_snapshot for result in self._session_results),
            self._starting_equity(),
        )
        return BacktestSnapshot(
            enabled=self._configuration.enabled,
            lifecycle_state=self._state,
            mode=self._configuration.mode,
            run_id=self._run_id,
            deterministic_run_fingerprint=self._run_fingerprint,
            current_session_index=max(self._session_index, 0),
            total_sessions=len(self._configuration.session_paths),
            completed_sessions=sum(1 for item in self._session_results if item.backtest_outcome in {BacktestOutcome.PASSED, BacktestOutcome.COMPLETED_WITH_FINDINGS}),
            failed_sessions=sum(1 for item in self._session_results if item.backtest_outcome is BacktestOutcome.FAILED),
            stopped_sessions=sum(1 for item in self._session_results if item.backtest_outcome is BacktestOutcome.STOPPED),
            current_progress=BacktestSessionProgress(
                source_path=replay.source_path,
                session_id=replay.session_id,
                current_record_index=replay.current_record_index,
                total_records=replay.total_records,
                progress_percentage=replay.progress_percentage,
            ),
            aggregate_analytics=analytics,
            findings=tuple(self._findings[key] for key in self._finding_order if key in self._findings),
            latest_result=self._latest_result,
            started_at=self._started_at,
            ended_at=self._ended_at,
            outcome=self._latest_result.outcome if self._latest_result is not None else BacktestOutcome.NOT_RUN,
            final_summary=self._latest_result.final_summary if self._latest_result is not None else "-",
            report_path=self._latest_result.report_path if self._latest_result is not None else None,
            reproducibility_status=self._latest_result.reproducibility_status if self._latest_result is not None else ReproducibilityStatus.NOT_CHECKED,
            broker_order_calls=0,
        )

    def drain_for_cli(self) -> BacktestSnapshot:
        if self._state is BacktestLifecycleState.IDLE:
            self.start()
        while self._state is BacktestLifecycleState.RUNNING:
            self.process_batch()
        return self.snapshot()

    def _start_next_session(self) -> None:
        self._session_index += 1
        path = self._configuration.session_paths[self._session_index]
        self._session_event_hash = stable_digest({"events": ()})
        self._orchestrator.reset_backtest_run_state()
        if self._orchestrator.status is not RuntimeStatus.RUNNING:
            self._orchestrator.start()
        replay = self._replay()
        replay.reset(clear_persistent_data=False)
        loaded = replay.load_session(path)
        if loaded.lifecycle_state is ReplayLifecycleState.FAILED:
            self._finish_session(loaded)
            if self._configuration.stop_on_session_failure:
                self._fail("REPLAY_LOAD_FAILED", loaded.failure_reason or "Replay load failed.")
            return
        replay.start()
        self._add_finding(BacktestSeverity.INFO, "SESSION_STARTED", f"Session {loaded.session_id} started.")
        self._publish(BACKTEST_SESSION_STARTED)

    def _finish_session(self, replay_snapshot) -> None:
        if self._session_results and self._session_results[-1].session_identity == replay_snapshot.session_id:
            return
        for runtime in self._orchestrator.runtimes:
            runtime.stop()
        analytics = self._orchestrator.performance_analytics_engine.snapshot()
        findings = self._session_findings(replay_snapshot)
        outcome = self._session_outcome(replay_snapshot, findings)
        result = BacktestSessionResult(
            session_identity=replay_snapshot.session_id,
            source_path=replay_snapshot.source_path or Path("-"),
            trading_date=replay_snapshot.trading_date,
            instruments=tuple(getattr(item, "value", str(item)) for item in replay_snapshot.instruments),
            source_record_count=replay_snapshot.total_records,
            published_record_count=replay_snapshot.published_records,
            replay_outcome=replay_snapshot.final_outcome,
            backtest_outcome=outcome,
            started_at=replay_snapshot.started_at,
            ended_at=replay_snapshot.ended_at,
            duration_seconds=_duration(replay_snapshot.started_at, replay_snapshot.ended_at),
            signals_generated=sum(_paper(runtime).plans_received for runtime in self._orchestrator.snapshot().runtime_snapshots),
            orders_accepted=sum(_paper(runtime).orders_created for runtime in self._orchestrator.snapshot().runtime_snapshots),
            orders_rejected=0,
            trades_opened=sum(_paper(runtime).positions_opened for runtime in self._orchestrator.snapshot().runtime_snapshots),
            trades_closed=sum(_paper(runtime).positions_closed for runtime in self._orchestrator.snapshot().runtime_snapshots),
            open_positions=sum(1 for runtime in self._orchestrator.snapshot().runtime_snapshots if runtime.paper_trading and runtime.paper_trading.position is not None),
            analytics_snapshot=analytics,
            findings=findings,
            deterministic_session_fingerprint=self._session_fingerprints[self._session_index] if self._session_index >= 0 and self._session_index < len(self._session_fingerprints) else "-",
            session_event_digest=self._session_event_hash,
        )
        self._session_results = (*self._session_results, result)[-self._configuration.max_session_results :]
        if outcome is BacktestOutcome.FAILED:
            self._add_finding(BacktestSeverity.ERROR, "SESSION_FAILED", f"Session {replay_snapshot.session_id} failed.")
            self._publish(BACKTEST_SESSION_FAILED)
            if self._configuration.stop_on_session_failure:
                self._fail("SESSION_FAILED", "Backtest stopped after session failure.")
        else:
            self._add_finding(BacktestSeverity.INFO, "SESSION_COMPLETED", f"Session {replay_snapshot.session_id} completed.")
            self._publish(BACKTEST_SESSION_COMPLETED)

    def _complete(self) -> None:
        self._state = BacktestLifecycleState.COMPLETED
        self._ended_at = self._now()
        self._add_finding(BacktestSeverity.INFO, "BACKTEST_COMPLETED", "Backtest completed.")
        if all(result.trades_closed == 0 for result in self._session_results):
            self._add_finding(BacktestSeverity.INFO, "NO_TRADES", "No closed paper trades were produced.")
        outcome = BacktestOutcome.COMPLETED_WITH_FINDINGS if any(item.severity in {BacktestSeverity.WARNING, BacktestSeverity.ERROR, BacktestSeverity.CRITICAL} for item in self.snapshot().findings) else BacktestOutcome.PASSED
        self._persist_terminal(outcome, BACKTEST_COMPLETED)

    def _fail(self, code: str, message: str) -> None:
        if self._state in {BacktestLifecycleState.FAILED, BacktestLifecycleState.COMPLETED, BacktestLifecycleState.STOPPED}:
            return
        self._state = BacktestLifecycleState.FAILED
        self._ended_at = self._now()
        self._add_finding(BacktestSeverity.CRITICAL, code, message)
        self._persist_terminal(BacktestOutcome.FAILED, BACKTEST_FAILED)

    def _persist_terminal(self, outcome: BacktestOutcome, event_name: str) -> None:
        if self._terminal_persisted:
            return
        self._terminal_persisted = True
        findings = tuple(self._findings[key] for key in self._finding_order if key in self._findings)
        analytics = aggregate_analytics(tuple(item.analytics_snapshot for item in self._session_results), self._starting_equity())
        digest = session_result_digest(self._session_results, findings, self._run_fingerprint)
        reproducibility = ReproducibilityStatus.NOT_CHECKED
        if self._configuration.reproducibility_check_enabled:
            baseline = self._comparison_digest(self._run_fingerprint)
            if baseline is None:
                reproducibility = ReproducibilityStatus.NOT_CHECKED
            elif baseline == digest:
                reproducibility = ReproducibilityStatus.MATCH
                self._add_finding(BacktestSeverity.INFO, "REPRODUCIBILITY_MATCH", "Equivalent backtest result matched the comparison baseline.")
                findings = tuple(self._findings[key] for key in self._finding_order if key in self._findings)
            else:
                reproducibility = ReproducibilityStatus.MISMATCH
                self._add_finding(BacktestSeverity.ERROR, "REPRODUCIBILITY_MISMATCH", "Equivalent backtest result differed from the comparison baseline.")
                findings = tuple(self._findings[key] for key in self._finding_order if key in self._findings)
        result = BacktestBatchResult(
            run_id=self._run_id,
            deterministic_run_fingerprint=self._run_fingerprint,
            mode=self._configuration.mode,
            lifecycle_state=self._state,
            total_sessions=len(self._configuration.session_paths),
            completed_sessions=sum(1 for item in self._session_results if item.backtest_outcome in {BacktestOutcome.PASSED, BacktestOutcome.COMPLETED_WITH_FINDINGS}),
            failed_sessions=sum(1 for item in self._session_results if item.backtest_outcome is BacktestOutcome.FAILED),
            stopped_sessions=sum(1 for item in self._session_results if item.backtest_outcome is BacktestOutcome.STOPPED),
            aggregate_analytics=analytics,
            session_results=self._session_results,
            findings=findings,
            started_at=self._started_at,
            ended_at=self._ended_at,
            outcome=outcome,
            final_summary=_summary_text(outcome, self._session_results),
            report_path=None,
            reproducibility_status=reproducibility,
            result_digest=digest,
        )
        try:
            result = with_report_path(result, self._repository.write_report(result))
        except Exception as exc:
            self._add_finding(BacktestSeverity.ERROR, "REPORT_WRITE_FAILED", _safe_error(exc))
        self._last_result_digest = digest
        self._result_digests_by_fingerprint[self._run_fingerprint] = digest
        self._latest_result = result
        self._publish(event_name)

    def record_command_error(self, message: str) -> BacktestSnapshot:
        self._add_finding(BacktestSeverity.ERROR, "BACKTEST_COMMAND_FAILED", _safe_error(ValueError(message)))
        return self.snapshot()

    def _comparison_digest(self, fingerprint: str) -> str | None:
        digest = self._result_digests_by_fingerprint.get(fingerprint)
        if digest:
            return digest
        digest = self._repository.read_result_digest(fingerprint)
        if digest:
            self._result_digests_by_fingerprint[fingerprint] = digest
        return digest

    def _manifest_fingerprint(self, path: Path) -> str:
        replay = self._replay()
        previous = replay.snapshot()
        try:
            replay.reset(clear_persistent_data=False)
            loaded = replay.load_session(path)
            manifest = {
                "schema_version": "historical_replay_session_v1",
                "session_id": loaded.session_id,
                "trading_date": loaded.trading_date.isoformat() if loaded.trading_date else None,
                "instruments": [getattr(item, "value", str(item)) for item in loaded.instruments],
                "records": loaded.total_records,
                "first": loaded.first_event_timestamp.isoformat() if loaded.first_event_timestamp else None,
                "content_digest": _file_digest(path),
            }
            return stable_digest(manifest)
        finally:
            if previous.lifecycle_state is not ReplayLifecycleState.IDLE:
                replay.reset(clear_persistent_data=False)

    def _on_tick(self, payload) -> None:
        if self._routing_event or self._state is not BacktestLifecycleState.RUNNING or not isinstance(payload, Tick):
            return
        self._session_event_hash = stable_digest({"previous": self._session_event_hash, "tick": [payload.symbol.value, payload.timestamp.isoformat(), payload.last_price, payload.volume]})
        self._routing_event = True
        try:
            self._orchestrator.process_tick(payload)
        finally:
            self._routing_event = False

    def _on_option_chain(self, payload) -> None:
        if self._routing_event or self._state is not BacktestLifecycleState.RUNNING or not isinstance(payload, OptionChainSnapshot):
            return
        self._session_event_hash = stable_digest({"previous": self._session_event_hash, "option": [payload.symbol, payload.timestamp.isoformat(), len(payload.strikes)]})
        self._routing_event = True
        try:
            self._orchestrator.process_option_chain(payload.symbol, payload)
        finally:
            self._routing_event = False

    def _active_replay(self):
        return self._replay().snapshot() if self._orchestrator is not None else BacktestSessionProgress()

    def _replay(self):
        self._ensure_orchestrator()
        return self._orchestrator.historical_replay_engine

    def _ensure_orchestrator(self) -> None:
        if self._orchestrator is None:
            raise BacktestLifecycleError("deterministic backtest requires an ApplicationOrchestrator")

    def _ensure_live_inactive(self) -> None:
        if bool(self._live_market_data_active()) or bool(self._live_option_chain_active()):
            self._add_finding(BacktestSeverity.ERROR, "LIVE_RUNTIME_ACTIVE", "Backtest cannot start while live runtime is active.")
            raise BacktestLifecycleError("Backtest cannot start while live runtime is active.")

    def _session_findings(self, replay_snapshot) -> tuple[BacktestFinding, ...]:
        findings = []
        if replay_snapshot.final_outcome not in {ReplayOutcome.PASS, None}:
            findings.append(self._finding(BacktestSeverity.ERROR, "REPLAY_EXECUTION_FAILED", replay_snapshot.failure_reason or replay_snapshot.final_summary))
        for runtime in self._orchestrator.snapshot().runtime_snapshots:
            if runtime.paper_trading and runtime.paper_trading.position is not None:
                findings.append(self._finding(BacktestSeverity.WARNING, "OPEN_POSITIONS_REMAIN", "Open paper positions remain."))
        return tuple(findings[: self._configuration.max_findings])

    def _session_outcome(self, replay_snapshot, findings) -> BacktestOutcome:
        if replay_snapshot.final_outcome is ReplayOutcome.STOPPED:
            return BacktestOutcome.STOPPED
        if replay_snapshot.lifecycle_state is ReplayLifecycleState.FAILED or any(item.severity in {BacktestSeverity.ERROR, BacktestSeverity.CRITICAL} for item in findings):
            return BacktestOutcome.FAILED
        if findings:
            return BacktestOutcome.COMPLETED_WITH_FINDINGS
        return BacktestOutcome.PASSED

    def _add_finding(self, severity: BacktestSeverity, code: str, message: str) -> BacktestFinding:
        finding = self._finding(severity, code, message)
        key = (finding.code,)
        if key in self._findings:
            previous = self._findings[key]
            finding = replace(previous, occurrence_count=previous.occurrence_count + 1)
        elif len(self._finding_order) == self._finding_order.maxlen and self._finding_order:
            self._findings.pop(self._finding_order[0], None)
            self._finding_order.append(key)
        else:
            self._finding_order.append(key)
        self._findings[key] = finding
        return finding

    def _finding(self, severity: BacktestSeverity, code: str, message: str) -> BacktestFinding:
        return BacktestFinding(f"backtest-{next(self._counter)}", self._now(), severity, code, _safe_text(message))

    def _starting_equity(self) -> float | None:
        config = getattr(self._orchestrator.performance_analytics_engine, "_configuration", None) if self._orchestrator is not None else None
        return getattr(config, "starting_equity", None)

    def _require_state(self, *states) -> None:
        if self._state not in states:
            raise BacktestLifecycleError("invalid deterministic backtest lifecycle transition")

    def _publish(self, event_name: str) -> None:
        self._event_bus.publish(event_name, self.snapshot())
        if event_name != BACKTEST_UPDATED:
            self._event_bus.publish(BACKTEST_UPDATED, self.snapshot())

    def _now(self):
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("backtest clock must return timezone-aware datetime")
        return value.astimezone(IST)


def _paper(runtime_snapshot):
    diagnostics = runtime_snapshot.paper_trading.diagnostics if runtime_snapshot.paper_trading else None
    return diagnostics


def _duration(started, ended) -> float | None:
    if started is None or ended is None:
        return None
    return max((ended - started).total_seconds(), 0.0)


def _summary_text(outcome, results) -> str:
    return f"{outcome.value}: {len(results)} session(s)"


def _safe_error(exc) -> str:
    return _safe_text(str(exc).strip() or exc.__class__.__name__)


def _safe_text(value) -> str:
    text = str(value).strip() or "-"
    for token in ("api_key", "api_secret", "access_token", "request_token"):
        text = text.replace(token, "[REDACTED]")
    return text[:500]


def _file_digest(path: Path) -> str:
    digest = stable_digest({"file": "empty"})
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest = stable_digest({"previous": digest, "chunk": chunk.hex()})
    return digest
