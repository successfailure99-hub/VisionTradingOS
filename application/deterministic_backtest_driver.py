"""
Cooperative desktop driver for deterministic backtest playback.
"""

from __future__ import annotations

from engines.deterministic_backtest import BacktestLifecycleState, DeterministicBacktestEngine


class DeterministicBacktestDriver:
    def __init__(self, engine: DeterministicBacktestEngine):
        if not isinstance(engine, DeterministicBacktestEngine):
            raise TypeError("engine must be DeterministicBacktestEngine")
        self._engine = engine
        self._processing = False
        self._poll_count = 0

    @property
    def poll_count(self) -> int:
        return self._poll_count

    def poll(self):
        snapshot = self._engine.snapshot()
        if snapshot.lifecycle_state is not BacktestLifecycleState.RUNNING:
            return snapshot
        if self._processing:
            return snapshot
        self._processing = True
        try:
            self._poll_count += 1
            return self._engine.process_batch()
        finally:
            self._processing = False
