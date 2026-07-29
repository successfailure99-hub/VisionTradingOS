from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from application.enums import RuntimeInstrument
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.daily_ohlc import DailyOHLC
from engines.adr import ADRExpansionState, ADRExhaustionState
from engines.adr.models import ADRSnapshot
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.vision_method import (
    VisionCPRRelation,
    VisionCamarillaZone,
    VisionGapType,
    VisionLevelContextRequest,
    VisionLevelQuality,
    VisionPreviousDayRelation,
    VisionVWAPRelation,
    assemble_vision_level_context,
)
from engines.vwap.levels import VWAPLevels


NOW = datetime(2026, 7, 29, 9, 30, tzinfo=timezone.utc)
TODAY = date(2026, 7, 29)
PREVIOUS = date(2026, 7, 28)


def cpr() -> CPRLevels:
    return CPRLevels(
        trading_date=TODAY,
        previous_high=110.0,
        previous_low=90.0,
        previous_close=100.0,
        pivot=100.0,
        bc=99.0,
        tc=101.0,
        width=2.0,
        width_percentage=2.0,
    )


def camarilla() -> CamarillaLevels:
    return CamarillaLevels(
        trading_date=TODAY,
        previous_high=110.0,
        previous_low=90.0,
        previous_close=100.0,
        pivot=100.0,
        h3=103.0,
        h4=104.0,
        h5=105.0,
        h6=106.0,
        l3=97.0,
        l4=96.0,
        l5=95.0,
        l6=94.0,
    )


def previous_day() -> DailyOHLC:
    return DailyOHLC(PREVIOUS, open=98.0, high=110.0, low=90.0, close=100.0)


def adr() -> ADRSnapshot:
    return ADRSnapshot(
        trading_date=TODAY,
        instrument="NIFTY",
        adr_period=20,
        adr_value=100.0,
        today_high=150.0,
        today_low=50.0,
        today_range=100.0,
        adr_high=160.0,
        adr_low=60.0,
        range_consumed_pct=75.0,
        range_remaining_pct=25.0,
        expansion_state=ADRExpansionState.EXPANDING,
        exhaustion_state=ADRExhaustionState.NOT_EXHAUSTED,
        timestamp=NOW,
    )


def vwap(value=100.0, timestamp=NOW, symbol=Instrument.NIFTY) -> VWAPLevels:
    return VWAPLevels(
        symbol=symbol,
        trading_date=TODAY,
        timestamp=timestamp,
        vwap=value,
        cumulative_volume=1000,
        cumulative_price_volume=value * 1000,
    )


def request(**overrides) -> VisionLevelContextRequest:
    values = {
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": TimeFrame.FIVE_MINUTES,
        "trading_date": TODAY,
        "timestamp": NOW,
        "latest_price": 102.0,
        "opening_price": 111.0,
        "previous_day": previous_day(),
        "cpr": cpr(),
        "camarilla": camarilla(),
        "adr": adr(),
        "vwap": vwap(),
        "previous_price": 99.5,
        "virgin_cpr": True,
    }
    values.update(overrides)
    return VisionLevelContextRequest(**values)


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (102.0, VisionCPRRelation.ABOVE_CPR),
        (100.0, VisionCPRRelation.INSIDE_CPR),
        (98.0, VisionCPRRelation.BELOW_CPR),
    ],
)
def test_cpr_above_inside_and_below(price, expected):
    result = assemble_vision_level_context(request(latest_price=price))

    assert result.cpr_context.relation is expected


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (107.0, VisionCamarillaZone.ABOVE_H6),
        (105.5, VisionCamarillaZone.H5_H6),
        (104.5, VisionCamarillaZone.H4_H5),
        (103.5, VisionCamarillaZone.H3_H4),
        (100.0, VisionCamarillaZone.INSIDE_VALUE),
        (96.5, VisionCamarillaZone.L3_L4),
        (95.5, VisionCamarillaZone.L4_L5),
        (94.5, VisionCamarillaZone.L5_L6),
        (93.0, VisionCamarillaZone.BELOW_L6),
    ],
)
def test_camarilla_zones(price, expected):
    result = assemble_vision_level_context(request(latest_price=price))

    assert result.camarilla_context.zone is expected


@pytest.mark.parametrize(
    ("latest", "opening", "relation", "gap"),
    [
        (111.0, 111.0, VisionPreviousDayRelation.ABOVE_PREVIOUS_HIGH, VisionGapType.GAP_UP),
        (100.0, 100.0, VisionPreviousDayRelation.INSIDE_PREVIOUS_RANGE, VisionGapType.NO_GAP),
        (89.0, 89.0, VisionPreviousDayRelation.BELOW_PREVIOUS_LOW, VisionGapType.GAP_DOWN),
    ],
)
def test_previous_day_context_gap_virgin_cpr_and_distances(latest, opening, relation, gap):
    result = assemble_vision_level_context(request(latest_price=latest, opening_price=opening, virgin_cpr=True))

    assert result.previous_day_context.previous_day_relation is relation
    assert result.previous_day_context.gap_type is gap
    assert result.previous_day_context.virgin_cpr is True
    assert result.previous_day_context.distance_previous_high == latest - 110.0
    assert result.previous_day_context.distance_previous_low == latest - 90.0


def test_adr_context_contributes_quality_without_blocking():
    result = assemble_vision_level_context(request(latest_price=155.0))

    assert result.adr_context is not None
    assert result.adr_context.range_consumed_pct == 75.0
    assert result.adr_context.range_remaining_pct == 25.0
    assert result.adr_context.near_adr_resistance is True
    assert result.adr_context.near_adr_support is False
    assert result.adr_context.expansion == "expanding"
    assert result.quality is VisionLevelQuality.FULL


@pytest.mark.parametrize(
    ("latest", "previous", "vwap_value", "rejected", "expected"),
    [
        (100.3, None, 100.0, False, VisionVWAPRelation.ABOVE_VWAP),
        (99.7, None, 100.0, False, VisionVWAPRelation.BELOW_VWAP),
        (101.0, 99.0, 100.0, False, VisionVWAPRelation.CROSS_ABOVE),
        (99.0, 101.0, 100.0, False, VisionVWAPRelation.CROSS_BELOW),
        (100.01, None, 100.0, False, VisionVWAPRelation.RETEST),
        (101.0, None, 100.0, False, VisionVWAPRelation.FAR_ABOVE),
        (99.0, None, 100.0, False, VisionVWAPRelation.FAR_BELOW),
        (101.0, None, 100.0, True, VisionVWAPRelation.REJECT),
    ],
)
def test_vwap_relations(latest, previous, vwap_value, rejected, expected):
    result = assemble_vision_level_context(
        request(latest_price=latest, previous_price=previous, vwap=vwap(vwap_value), vwap_rejected=rejected)
    )

    assert result.vwap_context is not None
    assert result.vwap_context.relation is expected


def test_missing_adr_or_vwap_produces_partial_quality_without_rejection():
    missing_adr = assemble_vision_level_context(request(adr=None))
    missing_vwap = assemble_vision_level_context(request(vwap=None))
    missing_both = assemble_vision_level_context(request(adr=None, vwap=None))

    assert missing_adr.quality is VisionLevelQuality.PARTIAL
    assert missing_adr.missing_evidence == ("adr",)
    assert missing_vwap.quality is VisionLevelQuality.PARTIAL
    assert missing_vwap.missing_evidence == ("vwap",)
    assert missing_both.missing_evidence == ("adr", "vwap")


def test_validator_rejects_mismatched_instrument_timeframe_timezone_and_stale_snapshots():
    with pytest.raises(ValueError, match="instrument mismatch"):
        assemble_vision_level_context(request(), instrument=RuntimeInstrument.BANKNIFTY)
    with pytest.raises(ValueError, match="timeframe mismatch"):
        assemble_vision_level_context(request(), timeframe=TimeFrame.ONE_MINUTE)
    with pytest.raises(ValueError, match="adr instrument mismatch"):
        assemble_vision_level_context(request(adr=replace(adr(), instrument="BANKNIFTY")))
    with pytest.raises(ValueError, match="vwap instrument mismatch"):
        assemble_vision_level_context(request(vwap=vwap(symbol=Instrument.BANKNIFTY)))
    with pytest.raises(ValueError, match="timezone mismatch"):
        assemble_vision_level_context(request(vwap=vwap(timestamp=NOW.astimezone(timezone(timedelta(hours=5, minutes=30))))))
    with pytest.raises(ValueError, match="stale"):
        assemble_vision_level_context(request(vwap=vwap(timestamp=NOW - timedelta(minutes=10))))


def test_required_daily_level_date_validation_and_immutability():
    with pytest.raises(ValueError, match="cpr trading date mismatch"):
        assemble_vision_level_context(request(cpr=replace(cpr(), trading_date=PREVIOUS)))
    with pytest.raises(ValueError, match="camarilla trading date mismatch"):
        assemble_vision_level_context(request(camarilla=replace(camarilla(), trading_date=PREVIOUS)))
    with pytest.raises(ValueError, match="previous_day"):
        assemble_vision_level_context(request(previous_day=DailyOHLC(TODAY, 100.0, 110.0, 90.0, 100.0)))

    result = assemble_vision_level_context(request())
    with pytest.raises(FrozenInstanceError):
        result.quality = VisionLevelQuality.INSUFFICIENT


def test_vm02_boundary_creates_no_engine_calculator_runtime_or_dashboard_code():
    package = Path("engines/vision_method")

    assert not (package / "engine.py").exists()
    assert not (package / "calculator.py").exists()
    assert (package / "level_context.py").exists()
