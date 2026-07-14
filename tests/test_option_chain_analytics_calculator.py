from datetime import UTC, date, datetime

import pytest

from core.event_bus import EventBus
from engines.option_chain.enums import OptionType
from engines.option_chain.models import OptionChainSnapshot, OptionLeg, OptionStrike
from engines.option_chain.option_chain_engine import OptionChainEngine
from engines.option_chain_analytics import (
    OptionBuildUpType,
    OptionChainAnalyticsCalculator,
    OptionChainAnalyticsConfiguration,
    OptionLevelMigration,
    OptionPressureType,
    OptionTrendDirection,
)


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def snapshot(ts, call_price=10, call_oi=100, call_change=0, put_price=10, put_oi=100, put_change=0, underlying=25050):
    return OptionChainSnapshot(
        "NIFTY",
        "NSE",
        date(2026, 7, 30),
        ts,
        underlying,
        (
            OptionStrike(25000, OptionLeg(OptionType.CALL, call_price, call_oi, call_change, 1), OptionLeg(OptionType.PUT, put_price, put_oi, put_change, 1)),
            OptionStrike(25100, OptionLeg(OptionType.CALL, call_price + 1, call_oi + 1, call_change, 1), OptionLeg(OptionType.PUT, put_price + 1, put_oi + 1, put_change, 1)),
        ),
    )


def state(item):
    return OptionChainEngine(EventBus(), "NIFTY", "NSE", date(2026, 7, 30)).process(item)


def test_calculator_first_and_second_snapshot_temporal_analysis():
    first = snapshot(NOW)
    first_state = state(first)
    calc = OptionChainAnalyticsCalculator()
    initial = calc.calculate(current_snapshot=first, current_analysis=first_state, previous_snapshot=None, previous_analysis=None, configuration=OptionChainAnalyticsConfiguration())
    assert initial.strikes[0].call.build_up is OptionBuildUpType.INSUFFICIENT_DATA
    later = snapshot(datetime(2026, 7, 14, 9, 16, tzinfo=UTC), call_price=9, call_oi=120, call_change=20, put_price=9, put_oi=130, put_change=30)
    later_state = state(later)
    analytics = calc.calculate(current_snapshot=later, current_analysis=later_state, previous_snapshot=first, previous_analysis=first_state, configuration=OptionChainAnalyticsConfiguration())
    assert analytics.strikes[0].call.build_up is OptionBuildUpType.SHORT_BUILDUP
    assert analytics.strikes[0].put.build_up is OptionBuildUpType.SHORT_BUILDUP
    assert analytics.pressure.dominant_pressure in {OptionPressureType.PUT_WRITING, OptionPressureType.BALANCED, OptionPressureType.MIXED}
    assert analytics.pcr_trend.direction in {OptionTrendDirection.RISING, OptionTrendDirection.FALLING, OptionTrendDirection.FLAT}
    assert analytics.support_migration in OptionLevelMigration
    with pytest.raises(ValueError):
        calc.calculate(current_snapshot=OptionChainSnapshot("BANKNIFTY", "NSE", date(2026, 7, 30), NOW, 1, first.strikes), current_analysis=first_state, previous_snapshot=None, previous_analysis=None, configuration=OptionChainAnalyticsConfiguration())
