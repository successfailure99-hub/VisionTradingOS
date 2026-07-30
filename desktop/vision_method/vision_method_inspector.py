"""
Read-only Vision Method inspector.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget

from dashboard import formatters
from dashboard.widgets import FieldGrid, MetricCard, StatusBadge
from engines.vision_method import (
    VisionADRContext,
    VisionMethodSnapshot,
    VisionMethodValidationReport,
    VisionVWAPContext,
)


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


def _snapshot_values(snapshot: VisionMethodSnapshot) -> dict[str, str]:
    level = snapshot.level_context
    previous = snapshot.previous_day_context
    opening = snapshot.opening_range_context
    structure = snapshot.structure_context
    events = snapshot.structure_event_context
    liquidity = snapshot.liquidity_context
    setup = snapshot.setup_qualification_context
    option = snapshot.option_confirmation_context
    values = {
        "Instrument": snapshot.instrument.value,
        "Timeframe": snapshot.timeframe.value,
        "Timestamp": formatters.timestamp(snapshot.timestamp),
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
        "Method Candidate State": snapshot.candidate_state.value,
        "Method Quality": snapshot.quality,
    }
    return values


def _report_values(report: VisionMethodValidationReport) -> dict[str, str]:
    return {
        "Validation Result": report.validation_result.value,
        "Completed Steps": formatters.integer(report.metrics.completed_steps),
        "Failed Steps": formatters.integer(report.metrics.failed_steps),
        "Missing Steps": formatters.integer(report.metrics.missing_steps),
        "Blocking Stage": report.metrics.blocking_stage or "-",
    }


def _empty_values() -> dict[str, str]:
    return {field: "-" for _, fields in _SECTION_FIELDS for field in fields} | {
        "Candidate State": "-",
        "Quality": "-",
        "Validation Result": "-",
    }


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


def _swing_price(swing) -> str:
    if swing is None:
        return "none"
    return formatters.price(swing.price)


_SECTION_FIELDS = (
    (
        "Header",
        (
            "Instrument",
            "Timeframe",
            "Timestamp",
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
        "Opening Range",
        (
            "Opening High",
            "Opening Low",
            "Opening Width",
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
        "Vision Method",
        ("Method Candidate State", "Method Quality"),
    ),
    (
        "Validation",
        ("Completed Steps", "Failed Steps", "Missing Steps", "Blocking Stage"),
    ),
)
