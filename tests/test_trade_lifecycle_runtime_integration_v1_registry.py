from threading import RLock

import pytest

from application.trade_lifecycle_runtime_integration_v1 import (
    TradeLifecycleCoordinatorRegistry,
)
from application.trade_lifecycle_v1 import TradeLifecycleStatus
from core.enums.instrument import Instrument
from tests.test_trade_lifecycle_v1_coordinator import coordinator


def test_registry_register_get_order_and_rlock():
    first = coordinator(Instrument.NIFTY)
    second = coordinator(Instrument.BANKNIFTY)
    registry = TradeLifecycleCoordinatorRegistry()

    registry.register(Instrument.NIFTY, first)
    registry.register(Instrument.BANKNIFTY, second)

    assert registry.get(Instrument.NIFTY) is first
    assert registry.instruments() == (Instrument.NIFTY, Instrument.BANKNIFTY)
    assert registry.coordinators() == (first, second)
    assert isinstance(registry._lock, RLock().__class__)


def test_registry_rejects_duplicates_and_instrument_mismatch():
    registry = TradeLifecycleCoordinatorRegistry()
    item = coordinator(Instrument.NIFTY)
    registry.register(Instrument.NIFTY, item)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(Instrument.NIFTY, coordinator(Instrument.NIFTY))
    with pytest.raises(ValueError, match="instrument mismatch"):
        registry.register(Instrument.BANKNIFTY, item)
    with pytest.raises(ValueError, match="not registered"):
        registry.get(Instrument.SENSEX)


def test_registry_missing_supported_instrument_raises_value_error():
    registry = TradeLifecycleCoordinatorRegistry()

    with pytest.raises(ValueError, match="not registered"):
        registry.get(Instrument.SENSEX)


def test_registry_clear_requires_no_running_coordinator():
    registry = TradeLifecycleCoordinatorRegistry()
    item = coordinator(Instrument.NIFTY)
    registry.register(Instrument.NIFTY, item)
    item.start()

    with pytest.raises(RuntimeError, match="running"):
        registry.clear()

    item.stop()
    assert item.snapshot().lifecycle_status is TradeLifecycleStatus.STOPPED
    registry.clear()
    assert registry.instruments() == ()
