from datetime import UTC, date, datetime

import pytest

from core.enums.instrument import Instrument
from core.event_bus import EventBus
from engines.option_chain.option_chain_engine import OptionChainEngine
from engines.option_chain_analytics import OptionChainAnalyticsConfiguration, OptionChainAnalyticsEngine
from tests.test_option_chain_analytics_calculator import snapshot


def state(item):
    return OptionChainEngine(EventBus(), "NIFTY", "NSE", date(2026, 7, 30)).process(item)


def test_engine_lifecycle_duplicates_corrections_and_history():
    engine = OptionChainAnalyticsEngine(underlying=Instrument.NIFTY, expiry=date(2026, 7, 30), configuration=OptionChainAnalyticsConfiguration(history_limit=2))
    assert engine.snapshot is None
    assert engine.is_ready is False
    first = snapshot(datetime(2026, 7, 14, 9, 15, tzinfo=UTC))
    one = engine.process(first, state(first))
    assert engine.is_ready is True
    assert engine.process(first, state(first)) is one
    second = snapshot(datetime(2026, 7, 14, 9, 16, tzinfo=UTC), call_price=9, call_oi=120)
    two = engine.update(second, state(second))
    corrected = snapshot(datetime(2026, 7, 14, 9, 16, tzinfo=UTC), call_price=8, call_oi=130)
    three = engine.update(corrected, state(corrected))
    assert three is not two
    assert len(engine.history()) == 2
    with pytest.raises(ValueError):
        engine.process(first, state(first))
    engine.reset()
    assert engine.snapshot is None
    assert engine.history() == ()
