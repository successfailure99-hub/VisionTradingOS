from datetime import UTC, date, datetime

from core.enums.instrument import Instrument
from core.event_bus import EventBus
from engines.option_chain.option_chain_engine import OptionChainEngine
from engines.option_chain_analytics import OptionBuildUpType, OptionChainAnalyticsEngine
from tests.test_option_chain_analytics_calculator import snapshot


def state(item):
    return OptionChainEngine(EventBus(), "NIFTY", "NSE", date(2026, 7, 30)).process(item)


def test_realistic_transition_sequence_and_same_timestamp_correction():
    engine = OptionChainAnalyticsEngine(underlying=Instrument.NIFTY, expiry=date(2026, 7, 30))
    first = snapshot(datetime(2026, 7, 14, 9, 15, tzinfo=UTC))
    engine.process(first, state(first))
    second = snapshot(datetime(2026, 7, 14, 9, 16, tzinfo=UTC), call_price=9, call_oi=120, call_change=20, put_price=11, put_oi=90, put_change=-10)
    analytics = engine.process(second, state(second))
    assert analytics.strikes[0].call.build_up is OptionBuildUpType.SHORT_BUILDUP
    assert analytics.strikes[0].put.build_up is OptionBuildUpType.SHORT_COVERING
    corrected = snapshot(datetime(2026, 7, 14, 9, 16, tzinfo=UTC), call_price=11, call_oi=90, call_change=-10, put_price=9, put_oi=120, put_change=20)
    corrected_analytics = engine.process(corrected, state(corrected))
    assert corrected_analytics.strikes[0].call.build_up is OptionBuildUpType.SHORT_COVERING
    assert len(engine.history()) == 2
