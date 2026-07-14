from datetime import UTC, date, datetime

from application.enums import ExecutionSafetyMode
from application.bootstrap import ApplicationBootstrap
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from core.models.candle import Candle
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context_v2 import (
    MarketConflictSeverity,
    MarketContextV2Engine,
    MarketContextV2Input,
    MarketDirection,
    MarketRegime,
    TradePosture,
)
from engines.option_chain.enums import OptionType, PositioningBias, PressureType
from engines.option_chain.models import (
    OptionChainSnapshot,
    OptionChainState,
    OptionLeg,
    OptionStrike,
    StrikeMetric,
)
from engines.option_chain_analytics.enums import (
    OptionAnalyticsBias,
    OptionLevelMigration,
    OptionPressureType,
    OptionTrendDirection,
)
from engines.option_chain_analytics.models import (
    OptionChainAnalyticsSnapshot,
    OptionMetricTrend,
    OptionPressureSummary,
)
from engines.price_action.enums import BreakType, StructureType, SwingType, Trend
from engines.price_action.models import PriceActionState, StructureBreak, SwingPoint
from engines.vwap.levels import VWAPLevels


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)
EXPIRY = date(2026, 7, 30)


def pa(trend):
    bullish = trend is Trend.BULLISH
    return PriceActionState(
        "NIFTY",
        "1m",
        10,
        Candle("NIFTY", "1m", NOW, NOW, 99.0, 101.0, 98.0, 100.0, 1000),
        trend,
        SwingPoint("NIFTY", "1m", SwingType.HIGH, StructureType.HIGHER_HIGH if bullish else StructureType.LOWER_HIGH, 101.0, NOW, NOW, 1),
        SwingPoint("NIFTY", "1m", SwingType.LOW, StructureType.HIGHER_LOW if bullish else StructureType.LOWER_LOW, 99.0, NOW, NOW, 1),
        None,
        None,
        StructureBreak(BreakType.BULLISH_BOS if bullish else BreakType.BEARISH_BOS, 100.0, 101.0, NOW, NOW),
    )


def option_snapshot(bias):
    leg = OptionLeg(OptionType.CALL, 100.0, 1000, 10, 100)
    strike = OptionStrike(100.0, leg, OptionLeg(OptionType.PUT, 90.0, 1200, 20, 100))
    source_snapshot = OptionChainSnapshot("NIFTY", "NFO", EXPIRY, NOW, 100.0, (strike,))
    source_state = OptionChainState(
        "NIFTY",
        "NFO",
        EXPIRY,
        NOW,
        100.0,
        100.0,
        1,
        1000,
        1200,
        10,
        20,
        1.2,
        2.0,
        StrikeMetric(100.0, 1000),
        StrikeMetric(100.0, 1200),
        StrikeMetric(100.0, 10),
        StrikeMetric(100.0, 20),
        101.0,
        99.0,
        100.0,
        PressureType.CALL_WRITING,
        PressureType.PUT_WRITING,
        PositioningBias.BULLISH,
        (strike,),
    )
    return OptionChainAnalyticsSnapshot(
        underlying=Instrument.NIFTY,
        expiry=EXPIRY,
        timestamp=NOW,
        source_snapshot=source_snapshot,
        source_analysis=source_state,
        strikes=(),
        pressure=OptionPressureSummary(0, 100, 0, 0, 0, 1, 0, 0, 1.0, OptionPressureType.PUT_WRITING),
        pcr_trend=OptionMetricTrend(1.2, 1.0, 0.2, OptionTrendDirection.RISING),
        change_oi_pcr_trend=OptionMetricTrend(2.0, 1.5, 0.5, OptionTrendDirection.RISING),
        max_pain_trend=OptionMetricTrend(100.0, 100.0, 0.0, OptionTrendDirection.FLAT),
        support_migration=OptionLevelMigration.SHIFTED_UP,
        resistance_migration=OptionLevelMigration.UNCHANGED,
        atm_migration=OptionLevelMigration.UNCHANGED,
        previous_support=98.0,
        current_support=99.0,
        previous_resistance=102.0,
        current_resistance=102.0,
        previous_atm_strike=100.0,
        current_atm_strike=100.0,
        bullish_score=5 if "bullish" in bias.value else 0,
        bearish_score=5 if "bearish" in bias.value else 0,
        bias=bias,
        rationale=("Option analytics are deterministic.",),
    )


def input_bundle(trend, bias, price):
    return MarketContextV2Input(
        instrument=Instrument.NIFTY,
        timestamp=NOW,
        current_price=price,
        price_action=pa(trend),
        option_chain_analytics=option_snapshot(bias),
        camarilla=CamarillaLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 103.0, 106.0, 112.0, 118.0, 97.0, 94.0, 88.0, 82.0),
        cpr=CPRLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 99.0, 101.0, 2.0, 2.0),
        vwap=VWAPLevels(Instrument.NIFTY, date(2026, 7, 14), NOW, 100.0, 1000, 100000.0),
    )


def test_no_network_aligned_bullish_bearish_and_primary_conflict():
    engine = MarketContextV2Engine(instrument=Instrument.NIFTY)
    bullish = engine.process(input_bundle(Trend.BULLISH, OptionAnalyticsBias.BULLISH, 108.0))
    assert bullish.direction in {MarketDirection.BULLISH, MarketDirection.STRONGLY_BULLISH}
    assert bullish.regime in {MarketRegime.TRENDING_UP, MarketRegime.BREAKOUT_ATTEMPT}
    assert bullish.trade_posture is TradePosture.LOOK_FOR_LONGS
    bearish = engine.process(input_bundle(Trend.BEARISH, OptionAnalyticsBias.BEARISH, 93.0))
    assert bearish.direction in {MarketDirection.BEARISH, MarketDirection.STRONGLY_BEARISH}
    assert bearish.trade_posture is TradePosture.LOOK_FOR_SHORTS
    conflict = engine.process(input_bundle(Trend.BULLISH, OptionAnalyticsBias.BEARISH, 108.0))
    assert conflict.direction is MarketDirection.CONFLICTED
    assert conflict.conflict_severity in {MarketConflictSeverity.HIGH, MarketConflictSeverity.CRITICAL}
    assert conflict.trade_posture is TradePosture.AVOID_NEW_TRADES


def test_application_defaults_remain_analysis_only_and_dry_run():
    lifecycle = ApplicationBootstrap().create_application()
    snapshot = lifecycle.snapshot().orchestrator_snapshot
    assert snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert snapshot.broker_mode is BrokerExecutionMode.DRY_RUN
