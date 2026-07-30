"""
Vision Method to trade-candidate adapter.

The adapter creates a non-executing candidate contract from the completed
Vision Method snapshot and validation report. It never calculates indicators,
order prices, risk, position size, or broker fields.
"""

from __future__ import annotations

import logging

from core.enums.exchange import Exchange
from engines.vision_method import (
    VisionCandidateState,
    VisionMethodSnapshot,
    VisionMethodValidationReport,
    validate_vision_method_snapshot,
    validate_vision_method_validation_report,
)

from .enums import TradeCandidateDirection, TradeCandidateState
from .models import TradeCandidate


LOGGER = logging.getLogger(__name__)


class VisionRuntimeAdapter:
    def __init__(self, exchange: Exchange = Exchange.NSE) -> None:
        if not isinstance(exchange, Exchange):
            raise TypeError("exchange must be Exchange.")
        self._exchange = exchange

    def adapt(
        self,
        snapshot: VisionMethodSnapshot,
        validation_report: VisionMethodValidationReport,
    ) -> TradeCandidate:
        snapshot = validate_vision_method_snapshot(snapshot)
        validation_report = validate_vision_method_validation_report(validation_report)
        _validate_matching_contract(snapshot, validation_report)

        state, direction = _candidate_mapping(snapshot.candidate_state)
        candidate = TradeCandidate(
            instrument=snapshot.instrument,
            exchange=self._exchange,
            timeframe=snapshot.timeframe,
            timestamp=snapshot.timestamp,
            candidate_state=state,
            direction=direction,
            entry_zone=_entry_zone(snapshot, state, direction),
            stop_loss_zone=_stop_loss_zone(snapshot, state, direction),
            target_zone=_target_zone(snapshot, state, direction),
            confidence=snapshot.quality,
            reason=_reason(snapshot, validation_report, state),
            snapshot_reference=_snapshot_reference(snapshot),
            validation_reference=_validation_reference(validation_report),
        )
        _log_candidate(candidate, snapshot.candidate_state)
        return candidate


def adapt_vision_method_to_trade_candidate(
    snapshot: VisionMethodSnapshot,
    validation_report: VisionMethodValidationReport,
    *,
    exchange: Exchange = Exchange.NSE,
) -> TradeCandidate:
    return VisionRuntimeAdapter(exchange=exchange).adapt(snapshot, validation_report)


def _validate_matching_contract(
    snapshot: VisionMethodSnapshot,
    validation_report: VisionMethodValidationReport,
) -> None:
    if snapshot.instrument is not validation_report.instrument:
        raise ValueError("snapshot and validation_report instrument mismatch.")
    if snapshot.timeframe is not validation_report.timeframe:
        raise ValueError("snapshot and validation_report timeframe mismatch.")
    if snapshot.timestamp != validation_report.timestamp:
        raise ValueError("snapshot and validation_report timestamp mismatch.")
    if snapshot.candidate_state is not validation_report.candidate_state:
        raise ValueError("snapshot and validation_report candidate_state mismatch.")


def _candidate_mapping(
    state: VisionCandidateState,
) -> tuple[TradeCandidateState, TradeCandidateDirection]:
    if state is VisionCandidateState.LONG_ELIGIBLE:
        return TradeCandidateState.LONG, TradeCandidateDirection.LONG
    if state is VisionCandidateState.SHORT_ELIGIBLE:
        return TradeCandidateState.SHORT, TradeCandidateDirection.SHORT
    if state is VisionCandidateState.PREPARE_LONG:
        return TradeCandidateState.WAITING_LONG, TradeCandidateDirection.LONG
    if state is VisionCandidateState.PREPARE_SHORT:
        return TradeCandidateState.WAITING_SHORT, TradeCandidateDirection.SHORT
    return TradeCandidateState.NO_CANDIDATE, TradeCandidateDirection.NONE


def _entry_zone(
    snapshot: VisionMethodSnapshot,
    state: TradeCandidateState,
    direction: TradeCandidateDirection,
) -> str:
    if state is TradeCandidateState.NO_CANDIDATE:
        return "Not applicable"
    opening_range = snapshot.opening_range_context
    if direction is TradeCandidateDirection.LONG:
        if opening_range.break_direction.value == "up":
            return "Opening Range Break"
        return _level_reference(snapshot, bullish=True)
    if opening_range.break_direction.value == "down":
        return "Opening Range Break"
    return _level_reference(snapshot, bullish=False)


def _stop_loss_zone(
    snapshot: VisionMethodSnapshot,
    state: TradeCandidateState,
    direction: TradeCandidateDirection,
) -> str:
    if state is TradeCandidateState.NO_CANDIDATE:
        return "Not applicable"
    if direction is TradeCandidateDirection.LONG:
        if snapshot.structure_context.current_swing_low is not None:
            return "Below Swing Low"
        return "Below Opening Range"
    if snapshot.structure_context.current_swing_high is not None:
        return "Above Swing High"
    return "Above Opening Range"


def _target_zone(
    snapshot: VisionMethodSnapshot,
    state: TradeCandidateState,
    direction: TradeCandidateDirection,
) -> str:
    if state is TradeCandidateState.NO_CANDIDATE:
        return "Not applicable"
    zone = snapshot.level_context.camarilla_context.zone.value.upper().replace("_", "-")
    previous = snapshot.previous_day_context.previous_day_relation.value
    if direction is TradeCandidateDirection.LONG:
        if "H3" in zone or "H4" in zone:
            return "H4"
        if previous != "above_previous_high":
            return "Previous High"
        return "ADR High"
    if "L3" in zone or "L4" in zone:
        return "L4"
    if previous != "below_previous_low":
        return "Previous Low"
    return "ADR Low"


def _level_reference(snapshot: VisionMethodSnapshot, *, bullish: bool) -> str:
    zone = snapshot.level_context.camarilla_context.zone.value.upper().replace("_", "-")
    if bullish:
        if zone.startswith("H"):
            return zone
        if snapshot.level_context.vwap_context is not None:
            return "VWAP Support"
        return "Current Price Context"
    if zone.startswith("L"):
        return zone
    if snapshot.level_context.vwap_context is not None:
        return "VWAP Resistance"
    return "Current Price Context"


def _reason(
    snapshot: VisionMethodSnapshot,
    validation_report: VisionMethodValidationReport,
    state: TradeCandidateState,
) -> str:
    if state is TradeCandidateState.NO_CANDIDATE:
        if snapshot.blocking_reasons:
            return "; ".join(snapshot.blocking_reasons)
        return f"Vision Method state {snapshot.candidate_state.value}"
    if snapshot.supporting_reasons:
        return "; ".join(snapshot.supporting_reasons)
    return f"Validation {validation_report.validation_result.value}"


def _snapshot_reference(snapshot: VisionMethodSnapshot) -> str:
    return ":".join(
        (
            "vision_method",
            snapshot.instrument.value,
            snapshot.timeframe.value,
            snapshot.timestamp.isoformat(),
            snapshot.candidate_state.value,
            snapshot.quality,
        )
    )


def _validation_reference(validation_report: VisionMethodValidationReport) -> str:
    return ":".join(
        (
            "vision_method_validation",
            validation_report.instrument.value,
            validation_report.timeframe.value,
            validation_report.timestamp.isoformat(),
            validation_report.validation_result.value,
        )
    )


def _log_candidate(candidate: TradeCandidate, source_state: VisionCandidateState) -> None:
    if candidate.candidate_state is TradeCandidateState.LONG:
        LOGGER.debug("[RuntimeAdapter] Candidate Created LONG")
    elif candidate.candidate_state is TradeCandidateState.SHORT:
        LOGGER.debug("[RuntimeAdapter] Candidate Created SHORT")
    elif source_state in (VisionCandidateState.WAIT, VisionCandidateState.OBSERVE):
        LOGGER.debug("[RuntimeAdapter] No Candidate %s", source_state.value.upper())
    else:
        LOGGER.debug("[RuntimeAdapter] Blocked %s", source_state.value.upper())
