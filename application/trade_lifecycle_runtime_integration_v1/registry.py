"""
Coordinator registry for Trade Lifecycle Runtime Integration V1.
"""

from threading import RLock

from application.trade_lifecycle_v1 import TradeLifecycleCoordinatorV1
from application.trade_lifecycle_v1.enums import TradeLifecycleStatus
from core.enums.instrument import Instrument
from engines.risk_management_v2.models import SUPPORTED_INSTRUMENTS


class TradeLifecycleCoordinatorRegistry:
    def __init__(self):
        self._coordinators: dict[Instrument, TradeLifecycleCoordinatorV1] = {}
        self._lock = RLock()

    def register(
        self,
        instrument: Instrument,
        coordinator: TradeLifecycleCoordinatorV1,
    ) -> None:
        if instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        if not isinstance(coordinator, TradeLifecycleCoordinatorV1):
            raise TypeError("coordinator must be TradeLifecycleCoordinatorV1")
        if coordinator.instrument is not instrument:
            raise ValueError("coordinator instrument mismatch")
        with self._lock:
            existing = self._coordinators.get(instrument)
            if existing is not None:
                if existing.snapshot().running:
                    raise RuntimeError("cannot replace a running coordinator")
                raise ValueError("coordinator already registered")
            self._coordinators[instrument] = coordinator

    def get(self, instrument: Instrument) -> TradeLifecycleCoordinatorV1:
        if instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        with self._lock:
            try:
                return self._coordinators[instrument]
            except KeyError as exc:
                raise ValueError("coordinator is not registered") from exc

    def instruments(self) -> tuple[Instrument, ...]:
        with self._lock:
            return tuple(self._coordinators)

    def coordinators(self) -> tuple[TradeLifecycleCoordinatorV1, ...]:
        with self._lock:
            return tuple(self._coordinators.values())

    def clear(self) -> None:
        with self._lock:
            if any(coordinator.snapshot().lifecycle_status is TradeLifecycleStatus.RUNNING for coordinator in self._coordinators.values()):
                raise RuntimeError("cannot clear registry while coordinators are running")
            self._coordinators.clear()
