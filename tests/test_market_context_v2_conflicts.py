from datetime import UTC, date, datetime

from core.enums.instrument import Instrument
from core.models.candle import Candle
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context_v2 import (
    MarketConflictSeverity,
    MarketContextV2Calculator,
    MarketContextV2Configuration,
    MarketContextV2Input,
    MarketDirection,
    TradePosture,
)
from engines.price_action.enums import BreakType, StructureType, SwingType, Trend
from engines.price_action.models import PriceActionState, StructureBreak, SwingPoint
from engines.vwap.levels import VWAPLevels


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


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


def calculate(price_action, price=93.0):
    return MarketContextV2Calculator().calculate(
        inputs=MarketContextV2Input(
            instrument=Instrument.NIFTY,
            timestamp=NOW,
            current_price=price,
            price_action=price_action,
            option_chain_analytics=None,
            camarilla=CamarillaLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 103.0, 106.0, 112.0, 118.0, 97.0, 94.0, 88.0, 82.0),
            cpr=CPRLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 99.0, 101.0, 2.0, 2.0),
            vwap=VWAPLevels(Instrument.NIFTY, date(2026, 7, 14), NOW, 100.0, 1000, 100000.0),
        ),
        configuration=MarketContextV2Configuration(),
    )


def test_primary_vs_secondary_conflict_lowers_confidence():
    result = calculate(pa(Trend.BULLISH), price=93.0)
    assert result.conflicts
    assert result.conflict_severity in {
        MarketConflictSeverity.MODERATE,
        MarketConflictSeverity.HIGH,
        MarketConflictSeverity.CRITICAL,
    }
    assert result.confidence < 1.0


def test_secondary_sources_cannot_override_primary_alignment():
    result = calculate(pa(Trend.BULLISH), price=93.0)
    assert result.direction in {MarketDirection.BULLISH, MarketDirection.STRONGLY_BULLISH, MarketDirection.CONFLICTED}
    assert result.trade_posture in {
        TradePosture.LOOK_FOR_LONGS,
        TradePosture.AVOID_NEW_TRADES,
    }
