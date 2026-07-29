from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.events import (
    VISION_METHOD_FAILED,
    VISION_METHOD_INVALID,
    VISION_METHOD_PARTIAL,
    VISION_METHOD_READY,
    VISION_METHOD_UPDATED,
)
from engines.vision_method import (
    VisionCandidateState,
    VisionLevelContext,
    VisionMarketRegime,
    VisionMethodSnapshot,
    VisionOpeningContext,
    VisionOpeningLocation,
    VisionOptionConfirmation,
    VisionPreviousDayContext,
    VisionStructureState,
    validate_vision_method_snapshot,
)


NOW = datetime(2026, 7, 29, 9, 30, tzinfo=timezone.utc)


def opening_context() -> VisionOpeningContext:
    return VisionOpeningContext(
        opening_location=VisionOpeningLocation.ABOVE_CPR,
        opening_price=24168.5,
        cpr_relation="above",
        camarilla_relation="near_h3",
        gap_type="gap_up",
    )


def previous_day_context() -> VisionPreviousDayContext:
    return VisionPreviousDayContext(
        previous_high=24310.0,
        previous_low=24107.7,
        previous_close=24168.5,
        virgin_cpr=False,
        distance_previous_high=141.5,
        distance_previous_low=60.8,
    )


def level_context() -> VisionLevelContext:
    return VisionLevelContext(
        cpr_context=("cpr", "above"),
        camarilla_context=("camarilla", "h3"),
        adr_context=("adr", "normal"),
        vwap_context=("vwap", "above"),
    )


def snapshot(**overrides) -> VisionMethodSnapshot:
    values = {
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": TimeFrame.FIVE_MINUTES,
        "timestamp": NOW,
        "opening_context": opening_context(),
        "previous_day_context": previous_day_context(),
        "level_context": level_context(),
        "market_regime": VisionMarketRegime.TREND_DAY,
        "candidate_state": VisionCandidateState.OBSERVE,
        "blocking_reasons": ("wait_for_opening_range",),
        "supporting_reasons": ("opened_above_cpr",),
        "quality": "medium",
    }
    values.update(overrides)
    return VisionMethodSnapshot(**values)


def test_enum_contracts_and_serialization_are_deterministic():
    assert VisionOpeningLocation.ABOVE_CPR.value == "above_cpr"
    assert VisionOpeningLocation.INSIDE_CPR.value == "inside_cpr"
    assert VisionOpeningLocation.BELOW_CPR.value == "below_cpr"
    assert VisionMarketRegime.UNKNOWN.value == "unknown"
    assert VisionStructureState.BULLISH.value == "bullish"
    assert VisionOptionConfirmation.CONTRADICTS.value == "contradicts"
    assert VisionCandidateState.PREPARE_LONG.value == "prepare_long"
    assert VisionCandidateState.INSUFFICIENT_DATA.value == "insufficient_data"


def test_vision_method_snapshot_construction_equality_and_validation():
    first = snapshot()
    second = snapshot()

    assert first == second
    assert first.instrument is RuntimeInstrument.NIFTY
    assert first.timeframe is TimeFrame.FIVE_MINUTES
    assert validate_vision_method_snapshot(
        first,
        instrument=RuntimeInstrument.NIFTY,
        timeframe=TimeFrame.FIVE_MINUTES,
    ) is first


def test_models_are_immutable():
    result = snapshot()

    with pytest.raises(FrozenInstanceError):
        result.quality = "high"
    with pytest.raises(FrozenInstanceError):
        result.opening_context.opening_price = 1.0


def test_timezone_aware_timestamp_is_required():
    with pytest.raises(ValueError, match="timezone-aware"):
        snapshot(timestamp=datetime(2026, 7, 29, 9, 30))


def test_missing_mandatory_context_is_rejected():
    with pytest.raises(TypeError, match="opening_context"):
        snapshot(opening_context=None)
    with pytest.raises(TypeError, match="previous_day_context"):
        snapshot(previous_day_context=None)
    with pytest.raises(TypeError, match="level_context"):
        snapshot(level_context=None)
    with pytest.raises(ValueError, match="adr_context"):
        VisionLevelContext(
            cpr_context=("cpr",),
            camarilla_context=("camarilla",),
            adr_context=None,
            vwap_context=("vwap",),
        )


def test_invalid_instrument_and_timeframe_are_rejected():
    with pytest.raises(TypeError, match="instrument"):
        snapshot(instrument="NIFTY")
    with pytest.raises(TypeError, match="timeframe"):
        snapshot(timeframe="5m")
    with pytest.raises(ValueError, match="instrument mismatch"):
        validate_vision_method_snapshot(snapshot(), instrument=RuntimeInstrument.BANKNIFTY)
    with pytest.raises(ValueError, match="timeframe mismatch"):
        validate_vision_method_snapshot(snapshot(), timeframe=TimeFrame.ONE_MINUTE)


def test_previous_day_contract_rejects_invalid_ranges():
    with pytest.raises(ValueError, match="previous_high"):
        VisionPreviousDayContext(
            previous_high=100.0,
            previous_low=110.0,
            previous_close=105.0,
            virgin_cpr=False,
            distance_previous_high=1.0,
            distance_previous_low=1.0,
        )
    with pytest.raises(ValueError, match="previous_close"):
        VisionPreviousDayContext(
            previous_high=110.0,
            previous_low=100.0,
            previous_close=120.0,
            virgin_cpr=False,
            distance_previous_high=1.0,
            distance_previous_low=1.0,
        )


def test_reason_fields_are_immutable_tuples_and_normalized():
    result = snapshot(blocking_reasons=("  wait  ",), supporting_reasons=(" opened above cpr ",))

    assert result.blocking_reasons == ("wait",)
    assert result.supporting_reasons == ("opened above cpr",)
    with pytest.raises(TypeError, match="blocking_reasons"):
        snapshot(blocking_reasons=["wait"])


def test_vision_method_events_are_declared_without_runtime_publishing():
    assert VISION_METHOD_UPDATED == "vision_method_updated"
    assert VISION_METHOD_PARTIAL == "vision_method_partial"
    assert VISION_METHOD_INVALID == "vision_method_invalid"
    assert VISION_METHOD_FAILED == "vision_method_failed"
    assert VISION_METHOD_READY == "vision_method_ready"
