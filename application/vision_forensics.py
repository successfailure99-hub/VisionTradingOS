"""Append-only Vision Method forensic trace owned by SymbolRuntime."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

from application.enums import RuntimeInstrument
from application.models import VisionForensicCounters
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from engines.runtime_adapter import TradeCandidate, TradeCandidateDirection, TradeCandidateState
from engines.risk_management_v2 import RiskDecision as RiskDecisionV2
from engines.vision_method import (
    VisionBOS,
    VisionCHoCH,
    VisionMSS,
    VisionMethodSnapshot,
    VisionMethodValidationReport,
    VisionSetupType,
)


class VisionForensicTrace:
    """Persist one deterministic row per closed Vision decision candle."""

    def __init__(
        self,
        *,
        instrument: RuntimeInstrument,
        decision_timeframe: TimeFrame,
        path: Path | str | None = None,
    ) -> None:
        if not isinstance(instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        if not isinstance(decision_timeframe, TimeFrame):
            raise TypeError("decision_timeframe must be TimeFrame")
        self._instrument = instrument
        self._decision_timeframe = decision_timeframe
        self._path = Path(path) if path is not None else Path("data") / "vision_forensics" / f"{instrument.value.lower()}_5m_trace.jsonl"
        self._runtime_session_id = "-"
        self._session_trading_date: date | None = None
        self._last_source_candle_timestamp: datetime | None = None
        self._counters = VisionForensicCounters("-", None, decision_timeframe.value)

    @property
    def counters(self) -> VisionForensicCounters:
        return self._counters

    @property
    def runtime_session_id(self) -> str:
        return self._runtime_session_id

    def reset_session(self, trading_date: date | None) -> None:
        session_id = _session_id(self._instrument, trading_date, self._decision_timeframe)
        if session_id == self._runtime_session_id:
            return
        self._runtime_session_id = session_id
        self._session_trading_date = trading_date
        self._last_source_candle_timestamp = None
        self._counters = VisionForensicCounters(session_id, trading_date, self._decision_timeframe.value)

    def record(
        self,
        *,
        snapshot: VisionMethodSnapshot,
        validation_report: VisionMethodValidationReport,
        source_candle: Candle,
        runtime_timestamp: datetime,
        trade_candidate: TradeCandidate,
        risk_snapshot: object | None,
        paper_position: object | None,
        decision_audit: object | None,
        option_sync_status: str,
        option_latency_ms: float | None,
    ) -> bool:
        if snapshot.instrument is not self._instrument:
            raise ValueError("forensic snapshot instrument mismatch")
        if snapshot.timeframe is not self._decision_timeframe:
            raise ValueError("forensic snapshot timeframe mismatch")
        if source_candle.timeframe != self._decision_timeframe.value:
            raise ValueError("forensic source candle timeframe mismatch")
        trading_date = source_candle.end_time.date()
        self.reset_session(trading_date)
        if snapshot.timestamp.date() != trading_date:
            raise ValueError("forensic Vision snapshot trading date does not match source candle")
        if validation_report.timestamp != snapshot.timestamp:
            raise ValueError("forensic validation timestamp mismatch")
        if trade_candidate.snapshot_reference and snapshot.timestamp.isoformat() not in trade_candidate.snapshot_reference:
            raise ValueError("forensic trade candidate contains stale Vision snapshot reference")
        if self._last_source_candle_timestamp == source_candle.end_time:
            return False

        record = self._record_payload(
            snapshot=snapshot,
            validation_report=validation_report,
            source_candle=source_candle,
            runtime_timestamp=runtime_timestamp,
            trade_candidate=trade_candidate,
            risk_snapshot=risk_snapshot,
            paper_position=paper_position,
            decision_audit=decision_audit,
            option_sync_status=option_sync_status,
            option_latency_ms=option_latency_ms,
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        self._last_source_candle_timestamp = source_candle.end_time
        self._counters = _increment_counters(self._counters, record)
        return True

    def _record_payload(
        self,
        *,
        snapshot: VisionMethodSnapshot,
        validation_report: VisionMethodValidationReport,
        source_candle: Candle,
        runtime_timestamp: datetime,
        trade_candidate: TradeCandidate,
        risk_snapshot: object | None,
        paper_position: object | None,
        decision_audit: object | None,
        option_sync_status: str,
        option_latency_ms: float | None,
    ) -> dict[str, Any]:
        level = snapshot.level_context
        opening_range = snapshot.opening_range_context
        structure = snapshot.structure_context
        events = snapshot.structure_event_context
        liquidity = snapshot.liquidity_context
        setup = snapshot.setup_qualification_context
        option = snapshot.option_confirmation_context
        entry = snapshot.entry_location_context
        pivot_plan = snapshot.pivot_flight_plan
        risk_decision = getattr(risk_snapshot, "decision", None)
        risk_decision_value = getattr(risk_decision, "value", str(risk_decision or ""))
        approved = risk_decision in {RiskDecisionV2.APPROVED, RiskDecisionV2.APPROVED_REDUCED} or risk_decision_value in {
            "approved",
            "approved_reduced",
        }
        paper_status = str(getattr(paper_position, "status", "")).lower()
        paper_opened = bool(paper_status in {"open", "partially_closed", "objective_reached"} or getattr(paper_position, "has_open_position", False))
        paper_closed = bool(paper_status in {"closed", "invalidated", "cancelled", "target_hit", "stop_hit"})
        option_candidate = getattr(risk_snapshot, "candidate", None)
        return {
            "runtime_session_id": self._runtime_session_id,
            "session_trading_date": _iso_date(self._session_trading_date),
            "instrument": snapshot.instrument.value,
            "decision_timeframe": snapshot.timeframe.value,
            "candle_start": source_candle.start_time.isoformat(),
            "candle_end": source_candle.end_time.isoformat(),
            "runtime_timestamp": runtime_timestamp.isoformat(),
            "source_candle_timestamp": source_candle.end_time.isoformat(),
            "price": {
                "open": source_candle.open,
                "high": source_candle.high,
                "low": source_candle.low,
                "close": source_candle.close,
            },
            "daily_context": {
                "cpr_position": level.cpr_context.relation.value,
                "camarilla_zone": level.camarilla_context.zone.value,
                "previous_day_position": level.previous_day_context.previous_day_relation.value
                if level.previous_day_context.previous_day_relation is not None
                else "unknown",
                "adr_used": level.adr_context.range_consumed_pct if level.adr_context is not None else None,
                "adr_remaining": level.adr_context.range_remaining_pct if level.adr_context is not None else None,
                "vwap_position": level.vwap_context.relation.value if level.vwap_context is not None else "unavailable",
            },
            "pivot_flight_plan": _pivot_flight_plan_payload(pivot_plan),
            "opening_range": {
                "state": opening_range.current_location.value,
                "break": opening_range.break_direction.value,
                "retest": opening_range.retest_state.value,
                "false_break": opening_range.false_break,
            },
            "structure": {
                "trend": structure.trend.value,
                "structure_state": structure.structure_state.value,
                "swing_high": _swing_price(structure.current_swing_high),
                "swing_low": _swing_price(structure.current_swing_low),
            },
            "structure_events": {
                "bullish_bos": events.bos is VisionBOS.BULLISH_BOS,
                "bearish_bos": events.bos is VisionBOS.BEARISH_BOS,
                "bullish_choch": events.choch is VisionCHoCH.BULLISH_CHOCH,
                "bearish_choch": events.choch is VisionCHoCH.BEARISH_CHOCH,
                "continuation": events.continuation.value,
                "reversal": events.reversal.value,
                "break_strength": events.break_strength.value,
                "mss": events.mss is VisionMSS.MARKET_STRUCTURE_SHIFT,
            },
            "liquidity": {
                "buy_side_sweep": "buy_side" in liquidity.liquidity_sweep.value,
                "sell_side_sweep": "sell_side" in liquidity.liquidity_sweep.value,
                "equal_highs": len(liquidity.equal_highs),
                "equal_lows": len(liquidity.equal_lows),
                "fvg": liquidity.fair_value_gap.direction.value if liquidity.fair_value_gap is not None else "none",
                "order_block": liquidity.order_block.direction.value if liquidity.order_block is not None else "none",
            },
            "setup_qualification": {
                "classification": setup.setup_type.value,
                "quality": setup.setup_quality.value,
                "supporting_reasons": setup.supporting_reasons,
                "blocking_reasons": setup.blocking_reasons,
            },
            "option_confirmation": {
                "state": option.confirmation_state.value,
                "supporting_factors": option.supporting_factors,
                "contradicting_factors": option.contradicting_factors,
                "neutral_factors": option.neutral_factors,
                "sync_status": option_sync_status,
                "latency_ms": option_latency_ms,
            },
            "entry_location": {
                "direction": entry.direction,
                "direction_quality": entry.direction_quality.value,
                "entry_location_state": entry.entry_location_state.value,
                "entry_location_quality": entry.entry_location_quality.value,
                "remaining_room": entry.remaining_room,
                "nearest_target_or_destination": entry.nearest_target_or_destination,
                "nearest_invalidation": entry.nearest_invalidation,
                "move_maturity": entry.move_maturity.value,
                "retest_state": entry.retest_state,
                "chase_risk": entry.chase_risk.value,
                "supporting_reasons": entry.location_supporting_reasons,
                "warning_reasons": entry.location_warning_reasons,
                "blocking_reasons": entry.location_blocking_reasons,
            },
            "vision_method": {
                "candidate_state": snapshot.candidate_state.value,
                "quality": snapshot.quality,
                "validation_result": validation_report.validation_result.value,
            },
            "runtime_adapter": {
                "trade_candidate_created": trade_candidate.candidate_state is not TradeCandidateState.NO_CANDIDATE,
                "candidate_direction": trade_candidate.direction.value,
                "candidate_reference": trade_candidate.snapshot_reference,
            },
            "risk": {
                "evaluated": risk_snapshot is not None and trade_candidate.direction is not TradeCandidateDirection.NONE,
                "approved": approved,
                "decision": risk_decision_value,
                "approved_quantity": getattr(risk_snapshot, "approved_quantity", None),
                "rejection_reason": getattr(decision_audit, "reason", None)
                if getattr(decision_audit, "rejected_at", None) == "Risk"
                else None,
            },
            "option_paper": {
                "constructor_invoked": option_candidate is not None,
                "selected_contract": getattr(option_candidate, "trading_symbol", None),
                "instrument_token": getattr(option_candidate, "instrument_token", None),
                "expiry": _iso_date(getattr(option_candidate, "expiry", None)),
                "strike": getattr(option_candidate, "strike", None),
                "option_type": getattr(getattr(option_candidate, "option_type", None), "value", None),
                "transaction_type": getattr(getattr(option_candidate, "transaction_type", None), "value", None),
                "moneyness": getattr(getattr(option_candidate, "moneyness", None), "value", None),
                "itm_steps": getattr(option_candidate, "itm_steps", None),
                "entry_premium": getattr(risk_snapshot, "entry_premium", None),
                "stop_premium": getattr(risk_snapshot, "stop_premium", None),
                "target_premium": getattr(risk_snapshot, "target_premium", None),
                "risk_result": risk_decision_value,
            },
            "paper": {
                "position_opened": paper_opened,
                "position_closed": paper_closed,
                "position_reference": getattr(paper_position, "trade_id", None) or getattr(paper_position, "position_id", None),
            },
            "vision_snapshot_reference": trade_candidate.snapshot_reference,
            "trade_candidate_reference": trade_candidate.snapshot_reference,
        }


def _increment_counters(counters: VisionForensicCounters, record: dict[str, Any]) -> VisionForensicCounters:
    vision = record["vision_method"]
    setup = record["setup_qualification"]
    events = record["structure_events"]
    adapter = record["runtime_adapter"]
    risk = record["risk"]
    paper = record["paper"]
    candidate_state = vision["candidate_state"]
    validation_result = vision["validation_result"]
    return replace(
        counters,
        candles_evaluated=counters.candles_evaluated + 1,
        structure_events_detected=counters.structure_events_detected
        + int(any((events["bullish_bos"], events["bearish_bos"], events["bullish_choch"], events["bearish_choch"], events["mss"]))),
        qualified_setups=counters.qualified_setups + int(setup["classification"] != VisionSetupType.NO_QUALITY_SETUP.value),
        prepare_long=counters.prepare_long + int(candidate_state == "prepare_long"),
        prepare_short=counters.prepare_short + int(candidate_state == "prepare_short"),
        observe=counters.observe + int(candidate_state == "observe"),
        avoid=counters.avoid + int(candidate_state == "avoid"),
        long_eligible=counters.long_eligible + int(candidate_state == "long_eligible"),
        short_eligible=counters.short_eligible + int(candidate_state == "short_eligible"),
        validation_pass=counters.validation_pass + int(validation_result == "valid"),
        validation_partial=counters.validation_partial + int(validation_result == "partial"),
        validation_failed=counters.validation_failed + int(validation_result in {"invalid", "conflict", "insufficient_data"}),
        trade_candidates_created=counters.trade_candidates_created + int(adapter["trade_candidate_created"]),
        risk_approved=counters.risk_approved + int(risk["approved"]),
        risk_rejected=counters.risk_rejected + int(risk["evaluated"] and not risk["approved"]),
        paper_positions_opened=counters.paper_positions_opened + int(paper["position_opened"]),
        paper_positions_closed=counters.paper_positions_closed + int(paper["position_closed"]),
    )


def _session_id(instrument: RuntimeInstrument, trading_date: date | None, timeframe: TimeFrame) -> str:
    return f"{instrument.value}:{_iso_date(trading_date) or 'unknown'}:{timeframe.value}"


def _iso_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _pivot_flight_plan_payload(plan: object | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "reference_session_date": _iso_date(getattr(plan, "reference_session_date", None)),
        "cpr_relationship": getattr(getattr(plan, "cpr_relationship", None), "value", None),
        "cpr_width_state": getattr(getattr(plan, "cpr_width_state", None), "value", None),
        "camarilla_relationship": getattr(getattr(plan, "camarilla_relationship", None), "value", None),
        "camarilla_width_state": getattr(getattr(plan, "camarilla_width_state", None), "value", None),
        "combined_context": getattr(getattr(plan, "combined_context_state", None), "value", None),
        "directional_prior": getattr(getattr(plan, "combined_directional_prior", None), "value", None),
        "expansion_tendency": getattr(getattr(plan, "expansion_tendency", None), "value", None),
        "balance_tendency": getattr(getattr(plan, "balance_tendency", None), "value", None),
        "opening_confirmation_required": getattr(plan, "opening_confirmation_required", None),
        "bullish_zones": tuple(getattr(zone, "label", "") for zone in getattr(plan, "preferred_bullish_action_zones", ())),
        "bearish_zones": tuple(getattr(zone, "label", "") for zone in getattr(plan, "preferred_bearish_action_zones", ())),
        "conflicting_reasons": tuple(getattr(plan, "conflicting_reasons", ())),
        "warnings": tuple(getattr(plan, "warnings", ())),
    }


def _swing_price(value: object | None) -> float | None:
    price = getattr(value, "price", None)
    return float(price) if price is not None else None
