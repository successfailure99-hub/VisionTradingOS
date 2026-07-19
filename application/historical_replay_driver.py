"""
Cooperative desktop driver for historical replay playback.
"""

from __future__ import annotations

from engines.historical_market_replay import HistoricalMarketReplayEngine, ReplayLifecycleState, ReplayMode


class HistoricalReplayDriver:
    def __init__(self, engine: HistoricalMarketReplayEngine):
        if not isinstance(engine, HistoricalMarketReplayEngine):
            raise TypeError("engine must be HistoricalMarketReplayEngine")
        self._engine = engine
        self._processing = False
        self._poll_count = 0

    @property
    def poll_count(self) -> int:
        return self._poll_count

    @property
    def processing(self) -> bool:
        return self._processing

    def poll(self):
        snapshot = self._engine.snapshot()
        if snapshot.lifecycle_state is not ReplayLifecycleState.RUNNING:
            return snapshot
        if snapshot.mode is ReplayMode.STEP:
            return snapshot
        if self._processing:
            return snapshot
        self._processing = True
        try:
            self._poll_count += 1
            return self._engine.process_batch()
        finally:
            self._processing = False
