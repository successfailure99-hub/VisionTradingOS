from datetime import UTC, date, datetime, timedelta

import pytest

from core.enums.instrument import Instrument
from core.models.candle import Candle
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context_v2 import (
    MarketContextV2Calculator,
    MarketContextV2Configuration,
    MarketContextV2Input,
    MarketContextReadiness,
    MarketDirection,
    TradePosture,
)
from engines.price_action.enums import BreakType, StructureType, SwingType, Trend
from engines.price_action.models import PriceActionState, StructureBreak, SwingPoint
from engines.vwap.levels import VWAPLevels


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def candle(symbol="NIFTY", end=NOW):
    return Candle(symbol, "1m", end, end, 99.0, 101.0, 98.0, 100.0, 1000)


def pa(symbol="NIFTY", trend=Trend.BULLISH, break_type=BreakType.BULLISH_BOS):
    high_type = StructureType.HIGHER_HIGH if trend is Trend.BULLISH else StructureType.LOWER_HIGH
    low_type = StructureType.HIGHER_LOW if trend is Trend.BULLISH else StructureType.LOWER_LOW
    return PriceActionState(
        symbol,
        "1m",
        10,
        candle(symbol),
        trend,
        SwingPoint(symbol, "1m", SwingType.HIGH, high_type, 101.0, NOW, NOW, 1),
        SwingPoint(symbol, "1m", SwingType.LOW, low_type, 99.0, NOW, NOW, 1),
        None,
        None,
        StructureBreak(break_type, 100.0, 101.0, NOW, NOW),
    )


def cpr():
    return CPRLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 99.0, 101.0, 2.0, 2.0)


def cam():
    return CamarillaLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 103.0, 106.0, 112.0, 118.0, 97.0, 94.0, 88.0, 82.0)


def inputs(**overrides):
    data = dict(
        instrument=Instrument.NIFTY,
        timestamp=NOW,
        current_price=108.0,
        price_action=pa(),
        option_chain_analytics=None,
        camarilla=cam(),
        cpr=cpr(),
        vwap=VWAPLevels(Instrument.NIFTY, date(2026, 7, 14), NOW, 100.0, 1000, 100000.0),
    )
    data.update(overrides)
    return MarketContextV2Input(**data)


def calculate(value):
    return MarketContextV2Calculator().calculate(
        inputs=value,
        configuration=MarketContextV2Configuration(),
    )


def test_primary_bullish_with_secondary_confirmation():
    result = calculate(inputs())
    assert result.readiness is MarketContextReadiness.READY
    assert result.direction in {MarketDirection.BULLISH, MarketDirection.STRONGLY_BULLISH}
    assert result.trade_posture is TradePosture.LOOK_FOR_LONGS
    assert result.bullish_score > result.bearish_score
    assert result.confidence > 0


def test_secondary_only_is_insufficient():
    result = calculate(inputs(price_action=None, option_chain_analytics=None))
    assert result.readiness is MarketContextReadiness.INSUFFICIENT
    assert result.direction is MarketDirection.INSUFFICIENT_DATA
    assert result.trade_posture is TradePosture.INSUFFICIENT_DATA
    assert result.confidence == 0.0


def test_wrong_instrument_and_future_source_rejected():
    with pytest.raises(ValueError):
        inputs(price_action=pa("BANKNIFTY"))
    with pytest.raises(ValueError):
        inputs(vwap=VWAPLevels(Instrument.NIFTY, date(2026, 7, 14), NOW + timedelta(minutes=1), 100.0, 1, 100.0))
