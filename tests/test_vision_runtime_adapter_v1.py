from dataclasses import FrozenInstanceError, replace

import pytest

from application.enums import RuntimeInstrument
from engines.runtime_adapter import (
    TradeCandidate,
    TradeCandidateDirection,
    TradeCandidateState,
    VisionRuntimeAdapter,
    adapt_vision_method_to_trade_candidate,
)
from engines.vision_method import (
    VisionBOS,
    VisionBreakDirection,
    VisionCPRRelation,
    VisionCamarillaZone,
    VisionCandidateState,
    VisionLevelQuality,
    VisionOpeningRangeState,
    VisionOptionConfirmation,
    VisionRangeLocation,
    VisionStructurePattern,
    VisionStructureTrend,
    VisionTriggerDirection,
    VisionTriggerType,
    VisionVWAPRelation,
    validate_vision_method,
)
from tests.test_vision_method_calculator_v1 import trigger
from tests.test_vision_method_validation_v1 import level, opening, option, setup, snapshot, structure, structure_event


def test_long_eligible_snapshot_creates_long_trade_candidate():
    item = snapshot()
    report = validate_vision_method(item)

    candidate = adapt_vision_method_to_trade_candidate(item, report)

    assert candidate.candidate_state is TradeCandidateState.LONG
    assert candidate.direction is TradeCandidateDirection.LONG
    assert candidate.confidence == item.quality
    assert candidate.entry_zone == "Opening Range Break"
    assert candidate.stop_loss_zone == "Below Swing Low"
    assert candidate.target_zone == "H4"
    assert "Above CPR" in candidate.reason
    assert item.timestamp.isoformat() in candidate.snapshot_reference
    assert report.validation_result.value in candidate.validation_reference


def test_short_eligible_snapshot_creates_short_trade_candidate():
    item = snapshot(
        level_context=level(
            cpr=VisionCPRRelation.BELOW_CPR,
            zone=VisionCamarillaZone.L3_L4,
            vwap=VisionVWAPRelation.BELOW_VWAP,
        ),
        opening_range_context=opening(
            state=VisionOpeningRangeState.BREAK_BELOW,
            direction=VisionBreakDirection.DOWN,
            location=VisionRangeLocation.BELOW_RANGE,
        ),
        structure_context=structure(trend=VisionStructureTrend.BEARISH, pattern=VisionStructurePattern.LL),
        structure_event_context=structure_event(bos=VisionBOS.BEARISH_BOS),
        setup_qualification_context=setup(supporting=("Below CPR", "Below L3", "Bearish BOS")),
        option_confirmation_context=option(supporting=("Call writing supports setup",)),
        price_action_trigger_context=trigger(
            direction=VisionTriggerDirection.BEARISH,
            trigger_type=VisionTriggerType.BEARISH_INITIATIVE_BREAKOUT,
        ),
    )
    report = validate_vision_method(item)

    candidate = VisionRuntimeAdapter().adapt(item, report)

    assert candidate.candidate_state is TradeCandidateState.SHORT
    assert candidate.direction is TradeCandidateDirection.SHORT
    assert candidate.entry_zone == "Opening Range Break"
    assert candidate.stop_loss_zone == "Above Swing High"
    assert candidate.target_zone == "L4"
    assert "Bearish BOS" in candidate.reason


@pytest.mark.parametrize(
    ("item", "expected_state", "expected_direction"),
    (
        (
            snapshot(
                opening_range_context=opening(
                    complete=False,
                    state=VisionOpeningRangeState.WAITING,
                    direction=VisionBreakDirection.NONE,
                    location=VisionRangeLocation.INSIDE_RANGE,
                    quality=VisionLevelQuality.PARTIAL,
                )
            ),
            TradeCandidateState.NO_CANDIDATE,
            TradeCandidateDirection.NONE,
        ),
        (
            snapshot(
                setup_qualification_context=setup(supporting=("Inside CPR",)),
                option_confirmation_context=option(state=VisionOptionConfirmation.NEUTRAL, neutral=("Mixed positioning",)),
            ),
            TradeCandidateState.NO_CANDIDATE,
            TradeCandidateDirection.NONE,
        ),
        (
            snapshot(option_confirmation_context=option(state=VisionOptionConfirmation.CONTRADICTS)),
            TradeCandidateState.WAITING_LONG,
            TradeCandidateDirection.LONG,
        ),
        (
            snapshot(
                level_context=level(quality=VisionLevelQuality.INSUFFICIENT),
                option_confirmation_context=option(state=VisionOptionConfirmation.UNAVAILABLE),
            ),
            TradeCandidateState.NO_CANDIDATE,
            TradeCandidateDirection.NONE,
        ),
    ),
)
def test_non_actionable_vision_states_create_no_candidate(item, expected_state, expected_direction):
    report = validate_vision_method(item)

    candidate = adapt_vision_method_to_trade_candidate(item, report)

    assert candidate.candidate_state is expected_state
    assert candidate.direction is expected_direction
    if expected_state is TradeCandidateState.NO_CANDIDATE:
        assert candidate.entry_zone == "Not applicable"
        assert candidate.stop_loss_zone == "Not applicable"
        assert candidate.target_zone == "Not applicable"
    else:
        assert candidate.entry_zone != "Not applicable"
        assert candidate.stop_loss_zone != "Not applicable"
        assert candidate.target_zone != "Not applicable"


def test_prepare_states_create_waiting_candidates_without_execution_fields():
    item = snapshot(
        option_confirmation_context=option(
            state=VisionOptionConfirmation.PARTIAL,
            contradicting=("Call writing caps setup",),
        )
    )
    report = validate_vision_method(item)

    candidate = adapt_vision_method_to_trade_candidate(item, report)

    assert item.candidate_state is VisionCandidateState.PREPARE_LONG
    assert candidate.candidate_state is TradeCandidateState.WAITING_LONG
    assert candidate.direction is TradeCandidateDirection.LONG
    assert candidate.entry_zone
    assert candidate.stop_loss_zone
    assert candidate.target_zone


def test_candidate_references_preserve_snapshot_and_validation_identity():
    item = snapshot()
    report = validate_vision_method(item)

    candidate = adapt_vision_method_to_trade_candidate(item, report)

    assert candidate.snapshot_reference == (
        f"vision_method:{item.instrument.value}:{item.timeframe.value}:"
        f"{item.timestamp.isoformat()}:{item.candidate_state.value}:{item.quality}"
    )
    assert candidate.validation_reference == (
        f"vision_method_validation:{report.instrument.value}:{report.timeframe.value}:"
        f"{report.timestamp.isoformat()}:{report.validation_result.value}"
    )


def test_trade_candidate_is_immutable():
    item = snapshot()
    report = validate_vision_method(item)
    candidate = adapt_vision_method_to_trade_candidate(item, report)

    with pytest.raises(FrozenInstanceError):
        candidate.reason = "changed"


def test_adapter_rejects_validation_report_for_different_snapshot():
    item = snapshot()
    report = validate_vision_method(item)
    bad_export = replace(report.export_record, instrument=RuntimeInstrument.BANKNIFTY.value)
    bad_report = replace(report, instrument=RuntimeInstrument.BANKNIFTY, export_record=bad_export)

    with pytest.raises(ValueError, match="instrument mismatch"):
        adapt_vision_method_to_trade_candidate(item, bad_report)


def test_trade_candidate_model_rejects_invalid_direction_mapping():
    item = snapshot()
    report = validate_vision_method(item)
    candidate = adapt_vision_method_to_trade_candidate(item, report)

    with pytest.raises(ValueError, match="candidate_state and direction"):
        TradeCandidate(
            instrument=candidate.instrument,
            exchange=candidate.exchange,
            timeframe=candidate.timeframe,
            timestamp=candidate.timestamp,
            candidate_state=TradeCandidateState.LONG,
            direction=TradeCandidateDirection.NONE,
            entry_zone=candidate.entry_zone,
            stop_loss_zone=candidate.stop_loss_zone,
            target_zone=candidate.target_zone,
            confidence=candidate.confidence,
            reason=candidate.reason,
            snapshot_reference=candidate.snapshot_reference,
            validation_reference=candidate.validation_reference,
        )
