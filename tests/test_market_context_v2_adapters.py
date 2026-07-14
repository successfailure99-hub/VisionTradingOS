from datetime import UTC, date, datetime

from core.models.candle import Candle
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context_v2 import (
    EvidenceDirection,
    EvidenceStrength,
    camarilla_evidence,
    cpr_evidence,
    price_action_evidence,
    vwap_evidence,
)
from engines.price_action.enums import BreakType, StructureType, SwingType, Trend
from engines.price_action.models import PriceActionState, StructureBreak, SwingPoint
from engines.vwap.levels import VWAPLevels
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def candle(close=100.0):
    return Candle("NIFTY", "1m", NOW, NOW, 99.0, 101.0, 98.0, close, 1000)


def swing(kind, structure, price):
    return SwingPoint("NIFTY", "1m", kind, structure, price, NOW, NOW, 1)


def price_action(trend=Trend.BULLISH, break_type=BreakType.BULLISH_BOS):
    return PriceActionState(
        symbol="NIFTY",
        timeframe="1m",
        candle_count=10,
        last_candle=candle(),
        trend=trend,
        latest_swing_high=swing(SwingType.HIGH, StructureType.HIGHER_HIGH, 101.0),
        latest_swing_low=swing(SwingType.LOW, StructureType.HIGHER_LOW, 99.0),
        previous_swing_high=None,
        previous_swing_low=None,
        latest_break=StructureBreak(break_type, 100.0, 101.0, NOW, NOW),
    )


def camarilla():
    return CamarillaLevels(
        trading_date=date(2026, 7, 14),
        previous_high=110.0,
        previous_low=90.0,
        previous_close=100.0,
        pivot=100.0,
        h3=103.0,
        h4=106.0,
        h5=112.0,
        h6=118.0,
        l3=97.0,
        l4=94.0,
        l5=88.0,
        l6=82.0,
    )


def cpr():
    return CPRLevels(date(2026, 7, 14), 110.0, 90.0, 100.0, 100.0, 99.0, 101.0, 2.0, 2.0)


def test_price_action_bullish_bearish_neutral_conflicted_and_unavailable():
    assert price_action_evidence(price_action(), timestamp=NOW, weight=4).direction is EvidenceDirection.BULLISH
    bearish = price_action(Trend.BEARISH, BreakType.BEARISH_BOS)
    bearish = PriceActionState(
        "NIFTY",
        "1m",
        10,
        candle(),
        Trend.BEARISH,
        swing(SwingType.HIGH, StructureType.LOWER_HIGH, 101.0),
        swing(SwingType.LOW, StructureType.LOWER_LOW, 99.0),
        None,
        None,
        StructureBreak(BreakType.BEARISH_BOS, 100.0, 99.0, NOW, NOW),
    )
    assert price_action_evidence(bearish, timestamp=NOW, weight=4).direction is EvidenceDirection.BEARISH
    ranged = PriceActionState("NIFTY", "1m", 10, candle(), Trend.RANGE, None, None, None, None, None)
    assert price_action_evidence(ranged, timestamp=NOW, weight=4).direction is EvidenceDirection.NEUTRAL
    mixed = price_action(Trend.BULLISH, BreakType.BEARISH_CHOCH)
    assert price_action_evidence(mixed, timestamp=NOW, weight=4).direction is EvidenceDirection.CONFLICTED
    assert price_action_evidence(None, timestamp=NOW, weight=4).direction is EvidenceDirection.UNAVAILABLE


def test_camarilla_cpr_and_vwap_boundaries():
    levels = camarilla()
    assert camarilla_evidence(levels, current_price=119.0, timestamp=NOW, weight=2).strength is EvidenceStrength.STRONG
    assert camarilla_evidence(levels, current_price=107.0, timestamp=NOW, weight=2).direction is EvidenceDirection.BULLISH
    assert camarilla_evidence(levels, current_price=100.0, timestamp=NOW, weight=2).direction is EvidenceDirection.NEUTRAL
    assert camarilla_evidence(levels, current_price=93.0, timestamp=NOW, weight=2).direction is EvidenceDirection.BEARISH
    assert camarilla_evidence(levels, current_price=81.0, timestamp=NOW, weight=2).strength is EvidenceStrength.STRONG
    cpr_levels = cpr()
    assert cpr_evidence(cpr_levels, current_price=102.0, timestamp=NOW, weight=2).direction is EvidenceDirection.BULLISH
    assert cpr_evidence(cpr_levels, current_price=98.0, timestamp=NOW, weight=2).direction is EvidenceDirection.BEARISH
    assert cpr_evidence(cpr_levels, current_price=100.0, timestamp=NOW, weight=2).direction is EvidenceDirection.NEUTRAL
    vwap = VWAPLevels(Instrument.NIFTY, date(2026, 7, 14), NOW, 100.0, 1000, 100000.0)
    assert vwap_evidence(vwap, current_price=101.0, timestamp=NOW, weight=1).direction is EvidenceDirection.BULLISH
    assert vwap_evidence(vwap, current_price=99.0, timestamp=NOW, weight=1).direction is EvidenceDirection.BEARISH
    assert vwap_evidence(vwap, current_price=100.0, timestamp=NOW, weight=1).direction is EvidenceDirection.NEUTRAL
