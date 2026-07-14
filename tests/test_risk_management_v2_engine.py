from datetime import timedelta
from threading import RLock

import pytest

from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import RISK_MANAGEMENT_V2_READY, RISK_MANAGEMENT_V2_UPDATED
from engines.risk_management_v2 import RiskManagementV2Configuration, RiskManagementV2Engine
from tests.test_risk_management_v2_calculator import account, config, risk_input, strategy


def test_constructor_initial_state_first_update_duplicate_and_events():
    events = []
    bus = EventBus()
    bus.subscribe(RISK_MANAGEMENT_V2_UPDATED, lambda payload: events.append(("updated", payload)))
    bus.subscribe(RISK_MANAGEMENT_V2_READY, lambda payload: events.append(("ready", payload)))
    engine = RiskManagementV2Engine(instrument=Instrument.NIFTY, configuration=config(), event_bus=bus)

    assert engine.snapshot is None
    assert engine.is_ready is False
    first_input = risk_input()
    first = engine.process(first_input)

    assert engine.snapshot is first
    assert engine.is_ready is True
    assert engine.update(first_input) is first
    assert [name for name, _ in events] == ["updated", "ready"]
    assert isinstance(engine._lock, RLock().__class__)


def test_newer_correction_stale_wrong_instrument_history_reset_clear_and_isolation():
    engine = RiskManagementV2Engine(
        instrument=Instrument.NIFTY,
        configuration=RiskManagementV2Configuration(maximum_position_quantity=10, history_limit=2),
    )
    first_strategy = strategy()
    first = engine.process(risk_input(first_strategy))
    corrected = engine.process(risk_input(first_strategy, account=account(first_strategy, available_capital=5000.0)))

    assert corrected is not first
    assert len(engine.history()) == 1

    later_strategy = strategy(minutes=1)
    later = engine.process(risk_input(later_strategy))
    assert engine.previous_snapshot is corrected

    stale_strategy = strategy(minutes=-1)
    with pytest.raises(ValueError):
        engine.process(risk_input(stale_strategy))
    assert engine.snapshot is later
    with pytest.raises(TypeError):
        engine.history()[0] = later

    other = RiskManagementV2Engine(instrument=Instrument.BANKNIFTY)
    assert other.snapshot is None
    with pytest.raises(ValueError):
        RiskManagementV2Engine(instrument=Instrument.SBI)
    with pytest.raises(ValueError):
        other.process(risk_input())

    engine.reset()
    assert engine.snapshot is None
    engine.process(risk_input(strategy(minutes=2)))
    engine.clear()
    assert engine.history() == ()


def test_history_is_bounded():
    engine = RiskManagementV2Engine(
        instrument=Instrument.NIFTY,
        configuration=RiskManagementV2Configuration(maximum_position_quantity=10, history_limit=2),
    )

    for minute in range(3):
        engine.process(risk_input(strategy(minutes=minute)))

    assert len(engine.history()) == 2
