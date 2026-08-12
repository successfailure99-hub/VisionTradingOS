"""
Read-only Vision Method inspector.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget

from dashboard import formatters
from dashboard.widgets import FieldGrid, MetricCard, StatusBadge
from engines.vision_method import (
    VisionContextAssemblyFailure,
    VisionADRContext,
    VisionMethodSnapshot,
    VisionMethodValidationReport,
    VisionVWAPContext,
)
from .status import VisionMethodLiveStatus


class VisionMethodInspector(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Vision Method", parent)
        self._labels: dict[str, QLabel | StatusBadge] = {}
        self._trace_labels: list[QLabel] = []
        self._cards = {
            "Candidate State": MetricCard("Candidate State"),
            "Quality": MetricCard("Quality"),
            "Validation Result": MetricCard("Validation Result"),
        }
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 18, 14, 14)
        root.setSpacing(12)
        root.setAlignment(Qt.AlignTop)
        for card in self._cards.values():
            root.addWidget(card)

        for title, fields in _SECTION_FIELDS:
            group = QGroupBox(title)
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(12, 14, 12, 12)
            grid = FieldGrid(fields)
            group_layout.addWidget(grid)
            root.addWidget(group)
            self._labels.update(grid.labels)

        trace_group = QGroupBox("Validation Trace")
        self._trace_layout = QVBoxLayout(trace_group)
        self._trace_layout.setContentsMargins(12, 14, 12, 12)
        self._trace_layout.setSpacing(8)
        root.addWidget(trace_group)
        self.render(None, None)

    def render(
        self,
        snapshot: VisionMethodSnapshot | None,
        report: VisionMethodValidationReport | None,
    ) -> None:
        if snapshot is not None and not isinstance(snapshot, VisionMethodSnapshot):
            raise TypeError("snapshot must be VisionMethodSnapshot or None.")
        if report is not None and not isinstance(report, VisionMethodValidationReport):
            raise TypeError("report must be VisionMethodValidationReport or None.")
        values = _empty_values()
        if snapshot is not None:
            values.update(_snapshot_values(snapshot))
        if report is not None:
            values.update(_report_values(report))
        for field, card in self._cards.items():
            card.set_value(values[field])
        for field, value in values.items():
            label = self._labels[field]
            if isinstance(label, StatusBadge):
                label.set_status_text(value)
            else:
                label.setText(formatters.text(value))
        self._render_trace(report)

    def render_live_status(
        self,
        status: VisionMethodLiveStatus,
        snapshot: VisionMethodSnapshot | None = None,
        report: VisionMethodValidationReport | None = None,
    ) -> None:
        if not isinstance(status, VisionMethodLiveStatus):
            raise TypeError("status must be VisionMethodLiveStatus.")
        if snapshot is not None and not isinstance(snapshot, VisionMethodSnapshot):
            raise TypeError("snapshot must be VisionMethodSnapshot or None.")
        if report is not None and not isinstance(report, VisionMethodValidationReport):
            raise TypeError("report must be VisionMethodValidationReport or None.")
        values = _empty_values()
        values.update(_diagnostic_values(status))
        values.update(_status_context_values(status))
        values.update(_status_values(status))
        if snapshot is not None:
            values.update(_snapshot_values(snapshot))
        if report is not None:
            values.update(_report_values(report))
        for field, card in self._cards.items():
            card.set_value(values[field])
        for field, value in values.items():
            label = self._labels[field]
            if isinstance(label, StatusBadge):
                label.set_status_text(value)
            else:
                label.setText(formatters.text(value))
        if report is not None:
            self._render_trace(report)
        else:
            self._render_status_trace(status)

    def render_failure(
        self,
        failure: VisionContextAssemblyFailure,
        *,
        instrument: str = "-",
        timeframe: str = "-",
        timestamp: str = "-",
    ) -> None:
        if not isinstance(failure, VisionContextAssemblyFailure):
            raise TypeError("failure must be VisionContextAssemblyFailure.")
        values = _empty_values()
        values.update(
            {
                "Instrument": instrument,
                "Timeframe": timeframe,
                "Timestamp": timestamp,
                "Candidate State": "insufficient_data",
                "Quality": "invalid",
                "Validation Result": "insufficient_data",
                "Assembly Failures": f"{failure.stage}: {failure.validation_message}",
                "Blocking Stage": failure.stage,
            }
        )
        for field, card in self._cards.items():
            card.set_value(values[field])
        for field, value in values.items():
            label = self._labels[field]
            if isinstance(label, StatusBadge):
                label.set_status_text(value)
            else:
                label.setText(formatters.text(value))
        self._render_failure_trace(failure)

    def _render_trace(self, report: VisionMethodValidationReport | None) -> None:
        while self._trace_labels:
            label = self._trace_labels.pop()
            self._trace_layout.removeWidget(label)
            label.deleteLater()
        lines = ("-",) if report is None else tuple(report.export_record.trace)
        for line in lines:
            label = QLabel(line)
            label.setWordWrap(True)
            label.setMinimumHeight(24)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._trace_layout.addWidget(label)
            self._trace_labels.append(label)

    def _render_status_trace(self, status: VisionMethodLiveStatus) -> None:
        while self._trace_labels:
            label = self._trace_labels.pop()
            self._trace_layout.removeWidget(label)
            label.deleteLater()
        lines = (
            f"STATUS | Vision Method Live | {status.runtime_state.value} | {status.blocking_reason}",
            f"FINAL | Vision Method | {status.validation_result} | {status.candidate_state}",
        )
        for line in lines:
            label = QLabel(line)
            label.setWordWrap(True)
            label.setMinimumHeight(24)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._trace_layout.addWidget(label)
            self._trace_labels.append(label)

    def _render_failure_trace(self, failure: VisionContextAssemblyFailure) -> None:
        while self._trace_labels:
            label = self._trace_labels.pop()
            self._trace_layout.removeWidget(label)
            label.deleteLater()
        lines = (
            f"STEP | {failure.stage} | {failure.status.value} | {failure.validation_message}",
            "FINAL | Vision Method | insufficient_data | Context assembly incomplete",
        )
        for line in lines:
            label = QLabel(line)
            label.setWordWrap(True)
            label.setMinimumHeight(24)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._trace_layout.addWidget(label)
            self._trace_labels.append(label)


def _snapshot_values(snapshot: VisionMethodSnapshot) -> dict[str, str]:
    level = snapshot.level_context
    previous = snapshot.previous_day_context
    opening = snapshot.opening_range_context
    structure = snapshot.structure_context
    events = snapshot.structure_event_context
    liquidity = snapshot.liquidity_context
    setup = snapshot.setup_qualification_context
    option = snapshot.option_confirmation_context
    entry = snapshot.entry_location_context
    pivot = snapshot.pivot_flight_plan
    opening_assessment = snapshot.pivot_opening_assessment
    confluence = snapshot.pivot_confluence_context
    trigger = snapshot.price_action_trigger_context
    values = {
        "Instrument": snapshot.instrument.value,
        "Timeframe": snapshot.timeframe.value,
        "Timestamp": formatters.timestamp(snapshot.timestamp),
        "Snapshot Generation": f"{snapshot.instrument.value}:{snapshot.timeframe.value}:{formatters.timestamp(snapshot.timestamp)}",
        "Vision Decision Timestamp": formatters.timestamp(snapshot.timestamp),
        "Candidate State": snapshot.candidate_state.value,
        "Quality": snapshot.quality,
        "CPR Position": level.cpr_context.relation.value,
        "Virgin CPR": formatters.yes_no(previous.virgin_cpr),
        "CPR Width": f"{level.cpr_context.width:.2f}",
        "Camarilla Zone": level.camarilla_context.zone.value,
        "Previous Day Position": previous.previous_day_relation.value if previous.previous_day_relation is not None else "-",
        "ADR Used": _adr_value(level.adr_context, "range_consumed_pct"),
        "ADR Remaining": _adr_value(level.adr_context, "range_remaining_pct"),
        "ADR Zone": _adr_zone(level.adr_context),
        "VWAP Position": _vwap_position(level.vwap_context),
        "VWAP Distance": _vwap_distance(level.vwap_context),
        "Opening High": formatters.price(opening.opening_high),
        "Opening Low": formatters.price(opening.opening_low),
        "Opening Width": formatters.price(opening.opening_width),
        "Opening Expected Candles": formatters.integer(opening.expected_candle_count),
        "Opening Actual Candles": formatters.integer(opening.actual_candle_count),
        "Opening Missing Candles": _missing_opening_candles(opening),
        "Opening Break": opening.break_direction.value,
        "Opening Retest": opening.retest_state.value,
        "Opening False Break": formatters.yes_no(opening.false_break),
        "Trend": structure.trend.value,
        "Structure State": structure.structure_state.value,
        "Swing High": _swing_price(structure.current_swing_high),
        "Swing Low": _swing_price(structure.current_swing_low),
        "Bullish BOS": formatters.yes_no(events.bos.value == "bullish_bos"),
        "Bearish BOS": formatters.yes_no(events.bos.value == "bearish_bos"),
        "Bullish CHOCH": formatters.yes_no(events.choch.value == "bullish_choch"),
        "Bearish CHOCH": formatters.yes_no(events.choch.value == "bearish_choch"),
        "Continuation": events.continuation.value,
        "Reversal": events.reversal.value,
        "Break Strength": events.break_strength.value,
        "Buy Side Sweep": formatters.yes_no(liquidity.liquidity_sweep.value == "buy_side_sweep"),
        "Sell Side Sweep": formatters.yes_no(liquidity.liquidity_sweep.value == "sell_side_sweep"),
        "Equal Highs": formatters.integer(len(liquidity.equal_highs)),
        "Equal Lows": formatters.integer(len(liquidity.equal_lows)),
        "Fair Value Gap": liquidity.fair_value_gap.direction.value if liquidity.fair_value_gap is not None else "-",
        "Order Block": liquidity.order_block.direction.value if liquidity.order_block is not None else "-",
        "Breaker": liquidity.breaker_block.state.value,
        "Mitigation": liquidity.mitigation.value,
        "Setup Classification": setup.setup_type.value,
        "Setup Quality": setup.setup_quality.value,
        "Setup Supporting Reasons": formatters.joined(setup.supporting_reasons),
        "Setup Blocking Reasons": formatters.joined(setup.blocking_reasons),
        "Option Confirmation": option.confirmation_state.value,
        "Option Supporting Factors": formatters.joined(option.supporting_factors),
        "Option Contradicting Factors": formatters.joined(option.contradicting_factors),
        "Option Neutral Factors": formatters.joined(option.neutral_factors),
        "Direction": entry.direction,
        "Direction Quality": entry.direction_quality.value,
        "Entry Location": entry.entry_location_state.value,
        "Entry Location Quality": entry.entry_location_quality.value,
        "Remaining Room": f"{entry.remaining_room:.2f}" if entry.remaining_room is not None else "-",
        "Nearest Destination": entry.nearest_target_or_destination,
        "Nearest Invalidation": entry.nearest_invalidation,
        "Move Maturity": entry.move_maturity.value,
        "Chase Risk": entry.chase_risk.value,
        "Retest State": entry.retest_state,
        "Location Supporting Reasons": formatters.joined(entry.location_supporting_reasons),
        "Location Warning Reasons": formatters.joined(entry.location_warning_reasons),
        "Location Blocking Reasons": formatters.joined(entry.location_blocking_reasons),
        "Final Candidate": snapshot.candidate_state.value,
        "Final Direction": _reason_suffix(snapshot.supporting_reasons, "Final direction "),
        "Final Trigger Gate": _reason_suffix(snapshot.supporting_reasons, "Final trigger gate"),
        "Final Location Gate": _reason_suffix(snapshot.supporting_reasons, "Final location gate"),
        "Final Option State": _reason_suffix(snapshot.supporting_reasons, "Final option state "),
        "Final Promotion Reason": _final_promotion_reason(snapshot.supporting_reasons),
        "Method Candidate State": snapshot.candidate_state.value,
        "Method Quality": snapshot.quality,
        "Assembly Failures": _assembly_failures(snapshot),
    }
    values.update(_pivot_values(pivot))
    values.update(_opening_assessment_values(opening_assessment))
    values.update(_pivot_confluence_values(confluence))
    values.update(_price_action_trigger_values(trigger))
    return values


def _reason_suffix(reasons: tuple[str, ...], prefix: str) -> str:
    for reason in reasons:
        if reason.startswith(prefix):
            suffix = reason[len(prefix) :].strip()
            return suffix[2:].strip() if suffix.startswith(": ") else suffix or reason
    return "-"


def _final_promotion_reason(reasons: tuple[str, ...]) -> str:
    for reason in reasons:
        if reason.startswith("Final promotion reason:") or reason.startswith("Final waiting reason:"):
            return reason.split(":", 1)[1].strip()
    return "-"


def _report_values(report: VisionMethodValidationReport) -> dict[str, str]:
    return {
        "Validation Result": report.validation_result.value,
        "Completed Steps": formatters.integer(report.metrics.completed_steps),
        "Failed Steps": formatters.integer(report.metrics.failed_steps),
        "Missing Steps": formatters.integer(report.metrics.missing_steps),
        "Blocking Stage": report.metrics.blocking_stage or "-",
    }


def _status_values(status: VisionMethodLiveStatus) -> dict[str, str]:
    return {
        "Runtime State": status.runtime_state.value,
        "Last Market Update": status.market_timestamp or "unavailable",
        "Last Inspector Refresh": formatters.timestamp(status.updated_at),
        "Market Data Age": _market_age(status),
        "Live Instrument": status.instrument or "unavailable",
        "Live Timeframe": status.timeframe or "unavailable",
        "Live Blocking Stage": status.blocking_stage or "none",
        "Blocking Reason": status.blocking_reason or "none",
        "Available Contexts": _joined_or_none(status.available_contexts),
        "Missing Contexts": _failure_list(status.missing_contexts),
        "Failed Contexts": _failure_list(status.failed_contexts),
        "Unexpected Error": status.unexpected_error or "none",
        "Assembly Failures": _failure_list((*status.missing_contexts, *status.failed_contexts)),
        "Instrument": status.instrument or "unavailable",
        "Timeframe": status.timeframe or "unavailable",
        "Timestamp": status.market_timestamp or "unavailable",
        "Snapshot Generation": (
            f"{status.instrument}:{status.timeframe}:{status.market_timestamp}"
            if status.instrument and status.timeframe and status.market_timestamp
            else "unavailable"
        ),
        "Vision Decision Timestamp": status.market_timestamp or "unavailable",
        "Candidate State": status.candidate_state,
        "Quality": status.quality,
        "Validation Result": status.validation_result,
        "Blocking Stage": status.blocking_stage or "none",
    }


def _status_context_values(status: VisionMethodLiveStatus) -> dict[str, str]:
    values: dict[str, str] = {}
    level = status.level_context
    if level is not None:
        previous = level.previous_day_context
        values.update(
            {
                "CPR Position": level.cpr_context.relation.value,
                "Virgin CPR": formatters.yes_no(previous.virgin_cpr),
                "CPR Width": f"{level.cpr_context.width:.2f}",
                "Camarilla Zone": level.camarilla_context.zone.value,
                "Previous Day Position": previous.previous_day_relation.value if previous.previous_day_relation is not None else "-",
                "ADR Used": _adr_value(level.adr_context, "range_consumed_pct"),
                "ADR Remaining": _adr_value(level.adr_context, "range_remaining_pct"),
                "ADR Zone": _adr_zone(level.adr_context),
                "VWAP Position": _vwap_position(level.vwap_context),
                "VWAP Distance": _vwap_distance(level.vwap_context),
            }
        )
    opening = status.opening_range_context
    if opening is not None:
        values.update(
            {
                "Opening High": formatters.price(opening.opening_high),
                "Opening Low": formatters.price(opening.opening_low),
                "Opening Width": formatters.price(opening.opening_width),
                "Opening Expected Candles": formatters.integer(opening.expected_candle_count),
                "Opening Actual Candles": formatters.integer(opening.actual_candle_count),
                "Opening Missing Candles": _missing_opening_candles(opening),
                "Opening Break": opening.break_direction.value,
                "Opening Retest": opening.retest_state.value,
                "Opening False Break": formatters.yes_no(opening.false_break),
            }
        )
    structure = status.structure_context
    if structure is not None:
        values.update(
            {
                "Trend": structure.trend.value,
                "Structure State": structure.structure_state.value,
                "Swing High": _swing_price(structure.current_swing_high),
                "Swing Low": _swing_price(structure.current_swing_low),
            }
        )
    events = status.structure_event_context
    if events is not None:
        values.update(
            {
                "Bullish BOS": formatters.yes_no(events.bos.value == "bullish_bos"),
                "Bearish BOS": formatters.yes_no(events.bos.value == "bearish_bos"),
                "Bullish CHOCH": formatters.yes_no(events.choch.value == "bullish_choch"),
                "Bearish CHOCH": formatters.yes_no(events.choch.value == "bearish_choch"),
                "Continuation": events.continuation.value,
                "Reversal": events.reversal.value,
                "Break Strength": events.break_strength.value,
            }
        )
    liquidity = status.liquidity_context
    if liquidity is not None:
        values.update(
            {
                "Buy Side Sweep": formatters.yes_no(liquidity.liquidity_sweep.value == "buy_side_sweep"),
                "Sell Side Sweep": formatters.yes_no(liquidity.liquidity_sweep.value == "sell_side_sweep"),
                "Equal Highs": formatters.integer(len(liquidity.equal_highs)),
                "Equal Lows": formatters.integer(len(liquidity.equal_lows)),
                "Fair Value Gap": liquidity.fair_value_gap.direction.value if liquidity.fair_value_gap is not None else "-",
                "Order Block": liquidity.order_block.direction.value if liquidity.order_block is not None else "-",
                "Breaker": liquidity.breaker_block.state.value,
                "Mitigation": liquidity.mitigation.value,
            }
        )
    setup = status.setup_qualification_context
    if setup is not None:
        values.update(
            {
                "Setup Classification": setup.setup_type.value,
                "Setup Quality": setup.setup_quality.value,
                "Setup Supporting Reasons": formatters.joined(setup.supporting_reasons),
                "Setup Blocking Reasons": formatters.joined(setup.blocking_reasons),
            }
        )
    option = status.option_confirmation_context
    if option is not None:
        values.update(
            {
                "Option Confirmation": option.confirmation_state.value,
                "Option Supporting Factors": formatters.joined(option.supporting_factors),
                "Option Contradicting Factors": formatters.joined(option.contradicting_factors),
                "Option Neutral Factors": formatters.joined(option.neutral_factors),
            }
        )
    values.update(_pivot_values(status.pivot_flight_plan))
    values.update(_opening_assessment_values(status.pivot_opening_assessment))
    values.update(_pivot_confluence_values(status.pivot_confluence_context))
    values.update(_price_action_trigger_values(status.price_action_trigger_context))
    return values


def _diagnostic_values(status: VisionMethodLiveStatus) -> dict[str, str]:
    values = {
        field: "not_evaluated"
        for _, fields in _SECTION_FIELDS
        for field in fields
        if field
        not in {
            "Runtime State",
            "Last Market Update",
            "Last Inspector Refresh",
            "Market Data Age",
            "Live Instrument",
            "Live Timeframe",
            "Live Blocking Stage",
            "Blocking Reason",
            "Available Contexts",
            "Missing Contexts",
            "Failed Contexts",
            "Unexpected Error",
            "Instrument",
            "Timeframe",
            "Timestamp",
            "Snapshot Generation",
            "Vision Decision Timestamp",
            "Candidate State",
            "Quality",
            "Validation Result",
        }
    }
    if status.runtime_state.value == "WAITING_FOR_MARKET_DATA":
        values.update(
            {
                "CPR Position": "unavailable",
                "Camarilla Zone": "unavailable",
                "ADR Used": "unavailable",
                "ADR Remaining": "unavailable",
                "ADR Zone": "unavailable",
                "VWAP Position": "unavailable",
                "VWAP Distance": "unavailable",
            }
        )
    for failure in (*status.missing_contexts, *status.failed_contexts):
        marker = failure.status.value
        stage = failure.stage.casefold()
        if "level" in stage:
            values.update(
                {
                    "CPR Position": marker,
                    "Camarilla Zone": marker,
                    "ADR Used": marker,
                    "ADR Remaining": marker,
                    "ADR Zone": marker,
                    "VWAP Position": marker,
                    "VWAP Distance": marker,
                }
            )
        elif "cpr" in stage:
            values.update({"CPR Position": marker, "Virgin CPR": marker, "CPR Width": marker})
        elif "camarilla" in stage:
            values.update({"Camarilla Zone": marker})
        elif "adr" in stage:
            values.update({"ADR Used": marker, "ADR Remaining": marker, "ADR Zone": marker})
        elif "vwap" in stage:
            values.update({"VWAP Position": marker, "VWAP Distance": marker})
        elif "pivot" in stage:
            values.update(
                {
                    "CPR Relationship": marker,
                    "CPR Width State": marker,
                    "Camarilla Relationship": marker,
                    "Camarilla Width State": marker,
                    "Combined Pivot Context": marker,
                    "Initial Pivot Bias": marker,
                    "Opening Confirmation Required": failure.validation_message,
                    "Top Hot Zone": marker,
                    "Hot Zone Band": marker,
                    "Hot Zone Role": marker,
                    "Hot Zone Quality": marker,
                    "Hot Zone Members": marker,
                    "Hot Zone Families": marker,
                    "Hot Zone Alignment": marker,
                    "Hot Zone Price Relation": marker,
                    "Hot Zone Status": marker,
                    "Hot Zone Reason": failure.validation_message,
                }
            )
        elif "candle" in stage:
            values.update(
                {
                    "Opening High": marker,
                    "Opening Low": marker,
                    "Opening Width": marker,
                    "Opening Expected Candles": marker,
                    "Opening Actual Candles": marker,
                    "Opening Missing Candles": marker,
                }
            )
        elif "opening range" in stage:
            values.update(
                {
                    "Opening High": marker,
                    "Opening Low": marker,
                    "Opening Width": marker,
                    "Opening Expected Candles": marker,
                    "Opening Actual Candles": marker,
                    "Opening Missing Candles": failure.validation_message,
                    "Opening Break": marker,
                    "Opening Retest": marker,
                    "Opening False Break": marker,
                }
            )
        elif "structure events" in stage:
            values.update(
                {
                    "Bullish BOS": marker,
                    "Bearish BOS": marker,
                    "Bullish CHOCH": marker,
                    "Bearish CHOCH": marker,
                    "Continuation": marker,
                    "Reversal": marker,
                    "Break Strength": marker,
                }
            )
        elif "structure" in stage:
            values.update({"Trend": marker, "Structure State": marker, "Swing High": marker, "Swing Low": marker})
        elif "liquidity" in stage:
            values.update(
                {
                    "Buy Side Sweep": marker,
                    "Sell Side Sweep": marker,
                    "Equal Highs": marker,
                    "Equal Lows": marker,
                    "Fair Value Gap": marker,
                    "Order Block": marker,
                    "Breaker": marker,
                    "Mitigation": marker,
                }
            )
        elif "setup" in stage:
            values.update(
                {
                    "Setup Classification": marker,
                    "Setup Quality": marker,
                    "Setup Blocking Reasons": failure.validation_message,
                }
            )
        elif "option" in stage:
            values.update(
                {
                    "Option Confirmation": marker,
                    "Option Neutral Factors": failure.validation_message,
                }
            )
        elif "entry location" in stage:
            values.update(
                {
                    "Entry Location": marker,
                    "Entry Location Quality": marker,
                    "Location Warning Reasons": failure.validation_message,
                }
            )
    return values


def _empty_values() -> dict[str, str]:
    return {field: "-" for _, fields in _SECTION_FIELDS for field in fields} | {
        "Candidate State": "-",
        "Quality": "-",
        "Validation Result": "-",
    }


def _assembly_failures(snapshot: VisionMethodSnapshot) -> str:
    if not snapshot.assembly_failures:
        return "none"
    return formatters.joined(
        tuple(f"{failure.stage} {failure.status.value}: {failure.validation_message}" for failure in snapshot.assembly_failures)
    )


def _market_age(status: VisionMethodLiveStatus) -> str:
    if status.market_data_age_seconds is None:
        return "unavailable"
    return f"{status.market_data_age_seconds:.0f}s"


def _joined_or_none(values: tuple[str, ...]) -> str:
    return formatters.joined(values) if values else "none"


def _failure_list(values: tuple[VisionContextAssemblyFailure, ...]) -> str:
    if not values:
        return "none"
    return formatters.joined(tuple(f"{item.stage} {item.status.value}: {item.validation_message}" for item in values))


def _adr_value(adr: VisionADRContext | None, field_name: str) -> str:
    if adr is None:
        return "unavailable"
    return f"{getattr(adr, field_name):.0f}%"


def _adr_zone(adr: VisionADRContext | None) -> str:
    if adr is None:
        return "unavailable"
    return f"{adr.expansion}; {adr.exhaustion}"


def _vwap_position(vwap: VisionVWAPContext | None) -> str:
    if vwap is None or vwap.relation.value == "unavailable":
        return "unavailable"
    if vwap.relation.value == "retest":
        return "touching"
    return vwap.relation.value


def _vwap_distance(vwap: VisionVWAPContext | None) -> str:
    if vwap is None:
        return "unavailable"
    return f"{vwap.distance_pct:.2f}%"


def _pivot_values(plan) -> dict[str, str]:
    if plan is None:
        return {}
    return {
        "CPR Relationship": plan.cpr_relationship.value,
        "CPR Width State": plan.cpr_width_state.value,
        "Camarilla Relationship": plan.camarilla_relationship.value,
        "Camarilla Width State": plan.camarilla_width_state.value,
        "Combined Pivot Context": plan.combined_context_state.value,
        "Initial Pivot Bias": plan.combined_directional_prior.value,
        "Expansion Tendency": plan.expansion_tendency.value,
        "Balance Tendency": plan.balance_tendency.value,
        "Opening Confirmation Required": formatters.yes_no(plan.opening_confirmation_required),
        "Bullish Action Zones": _pivot_zones(plan.preferred_bullish_action_zones),
        "Bearish Action Zones": _pivot_zones(plan.preferred_bearish_action_zones),
        "Pivot Warnings": _joined_or_none((*plan.conflicting_reasons, *plan.warnings)),
    }


def _pivot_zones(zones) -> str:
    return formatters.joined(tuple(f"{zone.label} ({zone.condition})" for zone in zones)) if zones else "none"


def _opening_assessment_values(assessment) -> dict[str, str]:
    if assessment is None:
        return {}
    return {
        "Opening Pre-Market Context": assessment.pre_market_context,
        "Opening Initial Bias": assessment.pre_market_directional_prior,
        "Canonical Opening Price": formatters.price(assessment.opening_price),
        "Canonical Opening Time": formatters.timestamp(assessment.opening_timestamp),
        "Opening Gap": assessment.gap_state.value,
        "Open Prior Range": assessment.prior_range_location.value,
        "Open CPR": assessment.cpr_location.value,
        "Open Camarilla": assessment.camarilla_location.value,
        "Open Value Location": assessment.pivot_value_location.value,
        "Plan Acceptance": assessment.opening_acceptance_state.value,
        "Active Opening Scenario": assessment.active_scenario.value,
        "Scenario Direction": assessment.scenario_direction.value,
        "Scenario Strength": assessment.scenario_strength.value,
        "Active Opening Zones": _opening_zones(assessment.activated_action_zones),
        "Rejected Opening Zones": _opening_zones(assessment.deactivated_action_zones),
        "Opening Supporting Reasons": _joined_or_none(assessment.supporting_reasons),
        "Opening Contradicting Reasons": _joined_or_none(assessment.contradicting_reasons),
        "Opening Warnings": _joined_or_none(assessment.warnings),
    }


def _opening_zones(zones) -> str:
    if not zones:
        return "none"
    return formatters.joined(tuple(f"{zone.zone_id.value}: {zone.reason}" for zone in zones))


def _pivot_confluence_values(context) -> dict[str, str]:
    if context is None:
        return {}
    if not context.hot_zones:
        return {
            "Top Hot Zone": "none",
            "Hot Zone Band": "none",
            "Hot Zone Role": "none",
            "Hot Zone Quality": context.quality.value,
            "Hot Zone Members": "none",
            "Hot Zone Families": "none",
            "Hot Zone Alignment": "none",
            "Hot Zone Price Relation": "none",
            "Hot Zone Status": context.status.value,
            "Hot Zone Reason": _joined_or_none(context.warnings),
        }
    zone = context.hot_zones[0]
    return {
        "Top Hot Zone": f"{zone.zone_type.value}",
        "Hot Zone Band": f"{formatters.price(zone.zone_low)} - {formatters.price(zone.zone_high)}",
        "Hot Zone Role": zone.directional_role.value,
        "Hot Zone Quality": f"{zone.quality.value} / {zone.strength.value}",
        "Hot Zone Members": formatters.joined(tuple(member.label for member in zone.member_references)),
        "Hot Zone Families": formatters.joined(tuple(family.value for family in zone.reference_families)),
        "Hot Zone Alignment": f"{zone.active_scenario_alignment.value}; opening {zone.opening_assessment_alignment.value}",
        "Hot Zone Price Relation": zone.current_price_relation.value,
        "Hot Zone Status": zone.status.value,
        "Hot Zone Reason": _joined_or_none((*zone.supporting_reasons, *zone.conflicting_reasons, *zone.warnings)),
    }


def _price_action_trigger_values(context) -> dict[str, str]:
    if context is None:
        return {}
    trigger = context.trigger
    return {
        "Trigger Zone": trigger.zone_reference,
        "Trigger Interaction": trigger.interaction_state.value,
        "Trigger Type": trigger.trigger_type.value,
        "Trigger Direction": trigger.trigger_direction.value,
        "Trigger Quality": trigger.trigger_quality.value,
        "Trigger Pattern": trigger.candlestick_pattern.value,
        "Trigger Break": trigger.break_state.value,
        "Trigger Acceptance": trigger.acceptance_state.value,
        "Trigger Retest": trigger.retest_state.value,
        "Trigger Structure Alignment": trigger.structure_alignment.value,
        "Trigger Liquidity Alignment": trigger.liquidity_alignment.value,
        "Trigger Opening Range Alignment": trigger.opening_range_alignment.value,
        "Trigger Scenario Alignment": trigger.scenario_alignment.value,
        "Trigger Reason": _joined_or_none(
            (
                *trigger.supporting_reasons,
                *trigger.contradicting_reasons,
                *trigger.warnings,
                *trigger.blocking_reasons,
            )
        ),
    }


def _swing_price(swing) -> str:
    if swing is None:
        return "none"
    return formatters.price(swing.price)


def _missing_opening_candles(opening) -> str:
    missing = tuple(getattr(opening, "missing_candle_timestamps", ()) or ())
    if not missing:
        return "none"
    return formatters.joined(tuple(formatters.timestamp(timestamp) for timestamp in missing))


_SECTION_FIELDS = (
    (
        "VISION METHOD LIVE STATUS",
        (
            "Runtime State",
            "Last Market Update",
            "Last Inspector Refresh",
            "Market Data Age",
            "Live Instrument",
            "Live Timeframe",
            "Live Blocking Stage",
            "Blocking Reason",
            "Available Contexts",
            "Missing Contexts",
            "Failed Contexts",
            "Unexpected Error",
        ),
    ),
    (
        "Header",
        (
            "Instrument",
            "Timeframe",
            "Timestamp",
            "Snapshot Generation",
            "Vision Decision Timestamp",
            "Candidate State",
            "Quality",
            "Validation Result",
        ),
    ),
    (
        "Level Context",
        (
            "CPR Position",
            "Virgin CPR",
            "CPR Width",
            "Camarilla Zone",
            "Previous Day Position",
            "ADR Used",
            "ADR Remaining",
            "ADR Zone",
            "VWAP Position",
            "VWAP Distance",
        ),
    ),
    (
        "Pivot Flight Plan",
        (
            "CPR Relationship",
            "CPR Width State",
            "Camarilla Relationship",
            "Camarilla Width State",
            "Combined Pivot Context",
            "Initial Pivot Bias",
            "Expansion Tendency",
            "Balance Tendency",
            "Opening Confirmation Required",
            "Bullish Action Zones",
            "Bearish Action Zones",
            "Pivot Warnings",
        ),
    ),
    (
        "Opening Assessment",
        (
            "Opening Pre-Market Context",
            "Opening Initial Bias",
            "Canonical Opening Price",
            "Canonical Opening Time",
            "Opening Gap",
            "Open Prior Range",
            "Open CPR",
            "Open Camarilla",
            "Open Value Location",
            "Plan Acceptance",
            "Active Opening Scenario",
            "Scenario Direction",
            "Scenario Strength",
            "Active Opening Zones",
            "Rejected Opening Zones",
            "Opening Supporting Reasons",
            "Opening Contradicting Reasons",
            "Opening Warnings",
        ),
    ),
    (
        "Pivot Confluence",
        (
            "Top Hot Zone",
            "Hot Zone Band",
            "Hot Zone Role",
            "Hot Zone Quality",
            "Hot Zone Members",
            "Hot Zone Families",
            "Hot Zone Alignment",
            "Hot Zone Price Relation",
            "Hot Zone Status",
            "Hot Zone Reason",
        ),
    ),
    (
        "Price-Action Trigger",
        (
            "Trigger Zone",
            "Trigger Interaction",
            "Trigger Type",
            "Trigger Direction",
            "Trigger Quality",
            "Trigger Pattern",
            "Trigger Break",
            "Trigger Acceptance",
            "Trigger Retest",
            "Trigger Structure Alignment",
            "Trigger Liquidity Alignment",
            "Trigger Opening Range Alignment",
            "Trigger Scenario Alignment",
            "Trigger Reason",
        ),
    ),
    (
        "Opening Range",
        (
            "Opening High",
            "Opening Low",
            "Opening Width",
            "Opening Expected Candles",
            "Opening Actual Candles",
            "Opening Missing Candles",
            "Opening Break",
            "Opening Retest",
            "Opening False Break",
        ),
    ),
    (
        "Structure",
        ("Trend", "Structure State", "Swing High", "Swing Low"),
    ),
    (
        "Structure Events",
        (
            "Bullish BOS",
            "Bearish BOS",
            "Bullish CHOCH",
            "Bearish CHOCH",
            "Continuation",
            "Reversal",
            "Break Strength",
        ),
    ),
    (
        "Liquidity",
        (
            "Buy Side Sweep",
            "Sell Side Sweep",
            "Equal Highs",
            "Equal Lows",
            "Fair Value Gap",
            "Order Block",
            "Breaker",
            "Mitigation",
        ),
    ),
    (
        "Setup Qualification",
        (
            "Setup Classification",
            "Setup Quality",
            "Setup Supporting Reasons",
            "Setup Blocking Reasons",
        ),
    ),
    (
        "Option Confirmation",
        (
            "Option Confirmation",
            "Option Supporting Factors",
            "Option Contradicting Factors",
            "Option Neutral Factors",
        ),
    ),
    (
        "Entry Location",
        (
            "Direction",
            "Direction Quality",
            "Entry Location",
            "Entry Location Quality",
            "Remaining Room",
            "Nearest Destination",
            "Nearest Invalidation",
            "Move Maturity",
            "Chase Risk",
            "Retest State",
            "Location Supporting Reasons",
            "Location Warning Reasons",
            "Location Blocking Reasons",
        ),
    ),
    (
        "Final Reasoning",
        (
            "Final Candidate",
            "Final Direction",
            "Final Trigger Gate",
            "Final Location Gate",
            "Final Option State",
            "Final Promotion Reason",
        ),
    ),
    (
        "Vision Method",
        ("Method Candidate State", "Method Quality", "Assembly Failures"),
    ),
    (
        "Validation",
        ("Completed Steps", "Failed Steps", "Missing Steps", "Blocking Stage"),
    ),
)
