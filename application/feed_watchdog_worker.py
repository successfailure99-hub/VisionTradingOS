"""
Application-owned worker for bounded live-feed watchdog polling.
"""

from __future__ import annotations

from threading import Event, RLock, Thread, current_thread
from typing import Callable


class LiveFeedWatchdogWorker:
    def __init__(self, callback: Callable[[], object], *, interval_seconds: float):
        if not callable(callback):
            raise TypeError("callback must be callable")
        if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float)):
            raise TypeError("interval_seconds must be numeric")
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._callback = callback
        self._interval_seconds = float(interval_seconds)
        self._stop_event = Event()
        self._lock = RLock()
        self._thread: Thread | None = None
        self._start_count = 0
        self._stop_count = 0
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def start_count(self) -> int:
        with self._lock:
            return self._start_count

    @property
    def stop_count(self) -> int:
        with self._lock:
            return self._stop_count

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = Thread(target=self._run, name="VisionLiveFeedWatchdog", daemon=True)
            self._thread.start()
            self._start_count += 1

    def stop(self, *, timeout: float = 2.0) -> None:
        with self._lock:
            thread = self._thread
            if thread is None:
                return
            self._stop_event.set()
        if thread is current_thread():
            return
        thread.join(timeout=timeout)
        with self._lock:
            if thread is self._thread and not thread.is_alive():
                self._thread = None
                self._stop_count += 1

    def tick_once(self) -> object:
        try:
            result = self._callback()
            self.last_error = None
            return result
        except Exception as exc:  # pragma: no cover - defensive containment
            self.last_error = f"{exc.__class__.__name__}: {exc}"
            return None

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            self.tick_once()
