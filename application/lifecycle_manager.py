"""
Application Bootstrap Lifecycle Manager V1.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock

from application.enums import RuntimeStatus
from application.models import OrchestratorSnapshot
from application.orchestrator import ApplicationOrchestrator


@dataclass(frozen=True, slots=True)
class LifecycleSnapshot:
    status: RuntimeStatus
    start_count: int
    stop_count: int
    restart_count: int
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    last_error: str | None
    orchestrator_snapshot: OrchestratorSnapshot


class ApplicationLifecycleManager:
    """
    Synchronous lifecycle owner for one ApplicationOrchestrator.

    The manager does not own engines directly. It starts, stops, restarts,
    resets, and snapshots the already-composed orchestrator. Restart from
    CREATED or STOPPED is treated as one restart request that starts the same
    orchestrator instance and finishes in RUNNING when successful.
    """

    def __init__(self, orchestrator: ApplicationOrchestrator):
        if not isinstance(orchestrator, ApplicationOrchestrator):
            raise TypeError("ApplicationLifecycleManager expects an ApplicationOrchestrator.")
        self._orchestrator = orchestrator
        self._status = RuntimeStatus.CREATED
        self._start_count = 0
        self._stop_count = 0
        self._restart_count = 0
        self._last_started_at: datetime | None = None
        self._last_stopped_at: datetime | None = None
        self._last_error: str | None = None
        self._lock = RLock()

    @property
    def orchestrator(self) -> ApplicationOrchestrator:
        return self._orchestrator

    @property
    def status(self) -> RuntimeStatus:
        with self._lock:
            return self._status

    def start(self) -> LifecycleSnapshot:
        with self._lock:
            if self._status is RuntimeStatus.RUNNING:
                return self._snapshot_unlocked()
            try:
                self._orchestrator.start()
            except Exception as exc:
                cleanup_error = self._attempt_cleanup()
                self._status = RuntimeStatus.ERROR
                self._last_error = self._format_error(exc, cleanup_error)
                raise
            self._status = RuntimeStatus.RUNNING
            self._start_count += 1
            self._last_started_at = self._utc_now()
            self._last_error = None
            return self._snapshot_unlocked()

    def stop(self) -> LifecycleSnapshot:
        with self._lock:
            if self._status is RuntimeStatus.STOPPED:
                return self._snapshot_unlocked()
            try:
                self._orchestrator.stop()
            except Exception as exc:
                self._status = RuntimeStatus.ERROR
                self._last_error = self._safe_error(exc)
                raise
            was_running = self._status is RuntimeStatus.RUNNING
            self._status = RuntimeStatus.STOPPED
            if was_running:
                self._stop_count += 1
            self._last_stopped_at = self._utc_now()
            return self._snapshot_unlocked()

    def restart(self) -> LifecycleSnapshot:
        with self._lock:
            try:
                if self._status is RuntimeStatus.RUNNING:
                    self.stop()
                self.start()
            except Exception as exc:
                self._status = RuntimeStatus.ERROR
                self._last_error = self._safe_error(exc)
                raise
            self._restart_count += 1
            return self._snapshot_unlocked()

    def reset(self) -> LifecycleSnapshot:
        with self._lock:
            self._orchestrator.reset_all()
            self._status = self._orchestrator.status
            return self._snapshot_unlocked()

    def snapshot(self) -> LifecycleSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def is_running(self) -> bool:
        return self.status is RuntimeStatus.RUNNING

    def is_stopped(self) -> bool:
        return self.status is RuntimeStatus.STOPPED

    def is_started(self) -> bool:
        return self.status in {RuntimeStatus.RUNNING, RuntimeStatus.STOPPED}

    def _snapshot_unlocked(self) -> LifecycleSnapshot:
        return LifecycleSnapshot(
            status=self._status,
            start_count=self._start_count,
            stop_count=self._stop_count,
            restart_count=self._restart_count,
            last_started_at=self._last_started_at,
            last_stopped_at=self._last_stopped_at,
            last_error=self._last_error,
            orchestrator_snapshot=self._orchestrator.snapshot(),
        )

    def _attempt_cleanup(self) -> Exception | None:
        try:
            self._orchestrator.stop()
        except Exception as exc:
            return exc
        return None

    def _format_error(self, original: Exception, cleanup: Exception | None) -> str:
        message = self._safe_error(original)
        if cleanup is not None:
            message = f"{message}; cleanup failed: {self._safe_error(cleanup)}"
        return message

    def _safe_error(self, exc: Exception) -> str:
        text = str(exc).strip()
        return f"{exc.__class__.__name__}: {text}" if text else exc.__class__.__name__

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)
