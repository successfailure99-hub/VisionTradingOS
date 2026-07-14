from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from core.enums.instrument import Instrument
from engines.option_chain.enums import OptionType
from engines.option_chain.models import OptionChainSnapshot, OptionChainState, OptionLeg, OptionStrike
from engines.option_chain_analytics import (
    OptionBuildUpType,
    OptionChainAnalyticsSnapshot,
    OptionLegAnalytics,
    OptionMetricTrend,
    OptionPressureSummary,
    OptionPressureType,
    OptionStrikeAnalytics,
    OptionTrendDirection,
    OptionLevelMigration,
    OptionAnalyticsBias,
)


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def test_models_are_frozen_slotted_and_validated():
    leg = OptionLegAnalytics(25000, OptionType.CALL, 10, None, None, 100, None, 0, None, OptionBuildUpType.INSUFFICIENT_DATA)
    with pytest.raises(FrozenInstanceError):
        leg.current_price = 11
    strike = OptionStrikeAnalytics(25000, leg, None, -10, OptionPressureType.INSUFFICIENT_DATA)
    pressure = OptionPressureSummary(0, 0, 0, 0, 0, 0, 0, 0, None, OptionPressureType.INSUFFICIENT_DATA)
    trend = OptionMetricTrend(None, None, None, OptionTrendDirection.UNKNOWN)
    source = OptionChainSnapshot("NIFTY", "NSE", date(2026, 7, 30), NOW, 25050, (OptionStrike(25000, OptionLeg(OptionType.CALL, 10, 100, 0, 1), None),))
    state = OptionChainState("NIFTY", "NSE", date(2026, 7, 30), NOW, 25050, 25000, 1, 100, 0, 0, 0, None, None, None, None, None, None, None, None, None, None, None, None, source.strikes)
    snapshot = OptionChainAnalyticsSnapshot(Instrument.NIFTY, date(2026, 7, 30), NOW, source, state, (strike,), pressure, trend, trend, trend, OptionLevelMigration.UNKNOWN, OptionLevelMigration.UNKNOWN, OptionLevelMigration.UNKNOWN, None, None, None, None, None, 25000, 0, 0, OptionAnalyticsBias.INSUFFICIENT_DATA, ("Previous comparable snapshot is unavailable.",))
    assert isinstance(snapshot.rationale, tuple)
    assert not hasattr(snapshot, "raw_tick")
    assert not hasattr(snapshot, "runtime")
    assert not hasattr(snapshot, "engine")
