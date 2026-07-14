from datetime import UTC, date, datetime

from core.enums.instrument import Instrument
from core.event_bus import EventBus
from engines.option_chain.option_chain_engine import OptionChainEngine
from engines.option_chain_analytics import OptionAnalyticsBias, OptionChainAnalyticsEngine
from tests.test_option_chain_analytics_calculator import snapshot


def test_no_network_existing_option_chain_engine_to_analytics_engine_flow():
    source_engine = OptionChainEngine(EventBus(), "NIFTY", "NSE", date(2026, 7, 30))
    analytics_engine = OptionChainAnalyticsEngine(underlying=Instrument.NIFTY, expiry=date(2026, 7, 30))
    first = snapshot(datetime(2026, 7, 14, 9, 15, tzinfo=UTC))
    first_state = source_engine.process(first)
    first_analytics = analytics_engine.process(first, first_state)
    assert first_analytics.bias is OptionAnalyticsBias.INSUFFICIENT_DATA
    second = snapshot(datetime(2026, 7, 14, 9, 16, tzinfo=UTC), call_price=9, call_oi=120, call_change=20, put_price=9, put_oi=130, put_change=30)
    second_state = source_engine.process(second)
    second_analytics = analytics_engine.process(second, second_state)
    assert second_analytics.source_analysis is second_state
    assert second_analytics.pressure.call_writing_oi >= 0
    assert isinstance(second_analytics.rationale, tuple)
    assert not hasattr(analytics_engine, "live_runtime")
