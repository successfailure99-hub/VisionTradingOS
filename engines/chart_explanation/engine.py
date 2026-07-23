"""
Chart Explanation Engine V1.
"""

from __future__ import annotations

import json
from datetime import datetime

from application.enums import RuntimeInstrument
from core import events
from core.base_engine import BaseEngine
from engines.expert_setup_classification.enums import (
    ExpertSetup,
    SetupQuality,
    SetupStability,
    SetupStrength,
)
from engines.expert_setup_classification.models import ExpertSetupClassificationSnapshot
from engines.market_state.enums import MarketEvidenceQuality, MarketState, VolatilityState
from engines.market_state.models import MarketStateSnapshot
from engines.multi_timeframe_evidence_fusion.enums import EvidenceCompleteness, EvidenceConflict, FusionDirection
from engines.multi_timeframe_evidence_fusion.models import MultiTimeframeEvidenceSnapshot

from .enums import ChartExplanationLifecycle, ExplanationQuality
from .models import ChartExplanationEngineSnapshot, ChartExplanationSnapshot


class ChartExplanationEngine(BaseEngine):
    """
    Deterministically translates intelligence snapshots into human text.

    The engine consumes only MultiTimeframeEvidenceSnapshot, MarketStateSnapshot,
    and ExpertSetupClassificationSnapshot values. It never calculates
    indicators, creates signals, or produces trading instructions.
    """

    def __init__(
        self,
        event_bus,
        *,
        instrument: RuntimeInstrument | str,
        maximum_source_age_seconds: int = 300,
    ) -> None:
        super().__init__(event_bus)
        self._instrument = _normalize_instrument(instrument)
        if (
            isinstance(maximum_source_age_seconds, bool)
            or not isinstance(maximum_source_age_seconds, int)
            or maximum_source_age_seconds < 0
        ):
            raise ValueError("maximum_source_age_seconds must be a non-negative integer.")
        self._maximum_source_age_seconds = maximum_source_age_seconds
        self._lifecycle_state = ChartExplanationLifecycle.CREATED
        self._last_snapshot: ChartExplanationSnapshot | None = None
        self._last_fingerprint: str | None = None
        self._explanation_count = 0
        self._updated_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error: str | None = None

    @property
    def state(self) -> ChartExplanationSnapshot | None:
        return self._last_snapshot

    def start(self) -> ChartExplanationEngineSnapshot:
        self._lifecycle_state = ChartExplanationLifecycle.READY
        self._event_bus.publish(events.CHART_EXPLANATION_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def stop(self) -> ChartExplanationEngineSnapshot:
        self._lifecycle_state = ChartExplanationLifecycle.STOPPED
        self._event_bus.publish(events.CHART_EXPLANATION_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def explain(
        self,
        fusion: MultiTimeframeEvidenceSnapshot | None,
        market_state: MarketStateSnapshot | None,
        setup: ExpertSetupClassificationSnapshot | None,
        *,
        timestamp: datetime,
    ) -> ChartExplanationSnapshot:
        return self.process(fusion, market_state, setup, timestamp=timestamp)

    def process(
        self,
        fusion: MultiTimeframeEvidenceSnapshot | None,
        market_state: MarketStateSnapshot | None,
        setup: ExpertSetupClassificationSnapshot | None,
        *,
        timestamp: datetime,
    ) -> ChartExplanationSnapshot:
        try:
            _validate_aware(timestamp, "timestamp")
            if fusion is None or market_state is None or setup is None:
                snapshot = self._missing_snapshot(timestamp, _missing_reason(fusion, market_state, setup))
                partial = True
            else:
                self._validate_inputs(fusion, market_state, setup)
                partial = _is_partial(fusion, market_state, setup, timestamp, self._maximum_source_age_seconds)
                snapshot = self._build_snapshot(fusion, market_state, setup, timestamp, partial=partial)
            if snapshot.source_fingerprint == self._last_fingerprint and self._last_snapshot is not None:
                return self._last_snapshot
        except (TypeError, ValueError):
            if self._last_error is None:
                self._last_error = "Chart explanation input is invalid."
            self._invalid_count += 1
            self._event_bus.publish(events.CHART_EXPLANATION_INVALID, self.snapshot())
            raise
        except Exception:
            self._failed_count += 1
            self._last_error = "Chart explanation failed."
            self._lifecycle_state = ChartExplanationLifecycle.FAILED
            self._event_bus.publish(events.CHART_EXPLANATION_FAILED, self.snapshot())
            raise

        self._last_snapshot = snapshot
        self._last_fingerprint = snapshot.source_fingerprint
        self._data = snapshot
        self._last_error = None
        self._explanation_count += 1
        self._lifecycle_state = ChartExplanationLifecycle.ACTIVE
        if partial:
            self._partial_count += 1
            self._event_bus.publish(events.CHART_EXPLANATION_PARTIAL, snapshot)
        else:
            self._updated_count += 1
            self._event_bus.publish(events.CHART_EXPLANATION_UPDATED, snapshot)
        self._event_bus.publish(events.CHART_EXPLANATION_STATE_UPDATED, self.snapshot())
        return snapshot

    def snapshot(self) -> ChartExplanationEngineSnapshot:
        return ChartExplanationEngineSnapshot(
            enabled=True,
            lifecycle_state=self._lifecycle_state,
            explanation_count=self._explanation_count,
            updated_count=self._updated_count,
            partial_count=self._partial_count,
            invalid_count=self._invalid_count,
            failed_count=self._failed_count,
            last_snapshot=self._last_snapshot,
            last_error=self._last_error,
        )

    def reset(self) -> ChartExplanationEngineSnapshot:
        super().clear()
        self._lifecycle_state = ChartExplanationLifecycle.READY
        self._last_snapshot = None
        self._last_fingerprint = None
        self._explanation_count = 0
        self._updated_count = 0
        self._partial_count = 0
        self._invalid_count = 0
        self._failed_count = 0
        self._last_error = None
        self._event_bus.publish(events.CHART_EXPLANATION_STATE_UPDATED, self.snapshot())
        return self.snapshot()

    def clear(self) -> None:
        self.reset()

    def _validate_inputs(
        self,
        fusion: MultiTimeframeEvidenceSnapshot,
        market_state: MarketStateSnapshot,
        setup: ExpertSetupClassificationSnapshot,
    ) -> None:
        if not isinstance(fusion, MultiTimeframeEvidenceSnapshot):
            self._last_error = "Chart explanation requires MultiTimeframeEvidenceSnapshot input."
            raise TypeError(self._last_error)
        if not isinstance(market_state, MarketStateSnapshot):
            self._last_error = "Chart explanation requires MarketStateSnapshot input."
            raise TypeError(self._last_error)
        if not isinstance(setup, ExpertSetupClassificationSnapshot):
            self._last_error = "Chart explanation requires ExpertSetupClassificationSnapshot input."
            raise TypeError(self._last_error)
        if (
            fusion.instrument is not self._instrument
            or market_state.instrument is not self._instrument
            or setup.instrument is not self._instrument
        ):
            self._last_error = "Chart explanation input instrument does not match engine."
            raise ValueError(self._last_error)

    def _missing_snapshot(self, timestamp: datetime, reason: str) -> ChartExplanationSnapshot:
        payload = {
            "instrument": self._instrument.value,
            "missing": reason,
            "quality": ExplanationQuality.LOW.value,
        }
        return ChartExplanationSnapshot(
            trading_date=timestamp.date(),
            instrument=self._instrument,
            headline="Low-Quality Setup",
            market_summary=f"The current chart explanation is incomplete because {reason} is missing.",
            primary_setup_explanation="No complete setup explanation is available from the deterministic intelligence layer.",
            supporting_evidence=(f"Missing input: {reason}.",),
            conflicting_evidence=(f"Missing input: {reason}.",),
            risk_notes=(f"Missing input: {reason}.",),
            explanation_quality=ExplanationQuality.LOW,
            timestamp=timestamp,
            source_fingerprint=_fingerprint(payload),
        )

    def _build_snapshot(
        self,
        fusion: MultiTimeframeEvidenceSnapshot,
        market_state: MarketStateSnapshot,
        setup: ExpertSetupClassificationSnapshot,
        timestamp: datetime,
        *,
        partial: bool,
    ) -> ChartExplanationSnapshot:
        quality = _quality(fusion, market_state, setup, partial)
        headline = _headline(fusion, setup, market_state, partial)
        summary = _market_summary(fusion, market_state, setup, partial)
        setup_text = _setup_explanation(setup, market_state, partial)
        supporting = _supporting_evidence(fusion, market_state, setup, partial)
        conflicting = _conflicting_evidence(fusion, market_state, setup, partial)
        risk_notes = _risk_notes(fusion, market_state, setup, partial)
        payload = {
            "headline": headline,
            "summary": summary,
            "setup": setup_text,
            "supporting": supporting,
            "conflicting": conflicting,
            "risk_notes": risk_notes,
            "quality": quality.value,
            "partial": partial,
        }
        return ChartExplanationSnapshot(
            trading_date=timestamp.date(),
            instrument=self._instrument,
            headline=headline,
            market_summary=summary,
            primary_setup_explanation=setup_text,
            supporting_evidence=supporting,
            conflicting_evidence=conflicting,
            risk_notes=risk_notes,
            explanation_quality=quality,
            timestamp=timestamp,
            source_fingerprint=_fingerprint(payload),
        )


def _headline(
    fusion: MultiTimeframeEvidenceSnapshot,
    setup: ExpertSetupClassificationSnapshot,
    market_state: MarketStateSnapshot,
    partial: bool,
) -> str:
    if partial or setup.primary_setup is ExpertSetup.NO_QUALITY_SETUP:
        return "Low-Quality Setup"
    if setup.primary_setup is ExpertSetup.TREND_CONTINUATION:
        return _trend_continuation_headline(fusion)
    if setup.primary_setup is ExpertSetup.TREND_DAY:
        return _trend_continuation_headline(fusion)
    if setup.primary_setup is ExpertSetup.RANGE_DAY:
        return "Range-Bound Market"
    if setup.primary_setup is ExpertSetup.BREAKOUT:
        return "Breakout Attempt"
    if setup.primary_setup is ExpertSetup.FAILED_BREAKOUT:
        return "Failed Breakout"
    if setup.primary_setup is ExpertSetup.BULL_TRAP:
        return "Bull Trap"
    if setup.primary_setup is ExpertSetup.BEAR_TRAP:
        return "Bear Trap"
    if setup.primary_setup is ExpertSetup.COMPRESSION:
        return "Compression Phase"
    if setup.primary_setup is ExpertSetup.EXPANSION:
        return "Expansion Phase"
    if setup.primary_setup is ExpertSetup.PULLBACK_CONTINUATION:
        return "Pullback Continuation"
    if setup.primary_setup is ExpertSetup.LIQUIDITY_SWEEP:
        return "Liquidity Sweep"
    if setup.primary_setup is ExpertSetup.REVERSAL_ATTEMPT:
        return "Transition Phase"
    if market_state.market_state is MarketState.TRANSITION:
        return "Transition Phase"
    return "Low-Quality Setup"


def _trend_continuation_headline(fusion: MultiTimeframeEvidenceSnapshot) -> str:
    direction = _dominant_direction(fusion)
    if direction is FusionDirection.BULLISH:
        return "Bullish Trend Continuation"
    if direction is FusionDirection.BEARISH:
        return "Bearish Trend Continuation"
    return "Trend Continuation"


def _dominant_direction(fusion: MultiTimeframeEvidenceSnapshot) -> FusionDirection:
    directions = {summary.timeframe: summary.direction for summary in fusion.summaries}
    return directions.get(fusion.dominant_timeframe, FusionDirection.UNKNOWN)


def _market_summary(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    setup: ExpertSetupClassificationSnapshot,
    partial: bool,
) -> str:
    completeness = "partial" if partial else "complete"
    return (
        f"The market is classified as {market_state.market_state.value} with "
        f"{market_state.evidence_quality.value} evidence quality. "
        f"Multi-timeframe evidence shows {fusion.evidence_agreement.value} with "
        f"{fusion.evidence_conflict.value} conflict, and the dominant timeframe is "
        f"{fusion.dominant_timeframe}. The current setup is "
        f"{setup.primary_setup.value} with {setup.setup_quality.value} setup quality "
        f"and {completeness} intelligence."
    )


def _setup_explanation(
    setup: ExpertSetupClassificationSnapshot,
    market_state: MarketStateSnapshot,
    partial: bool,
) -> str:
    if partial or setup.primary_setup is ExpertSetup.NO_QUALITY_SETUP:
        return "The setup quality is low because the deterministic intelligence layer is incomplete or degraded."
    return (
        f"The primary setup is {setup.primary_setup.value}. "
        f"Setup strength is {setup.setup_strength.value}, setup stability is "
        f"{setup.setup_stability.value}, and the surrounding market state is "
        f"{market_state.market_state.value}."
    )


def _supporting_evidence(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    setup: ExpertSetupClassificationSnapshot,
    partial: bool,
) -> tuple[str, ...]:
    values = [
        f"Market state: {market_state.market_state.value}.",
        f"Evidence agreement: {fusion.evidence_agreement.value}.",
        f"Dominant timeframe: {fusion.dominant_timeframe}.",
        f"Setup strength: {setup.setup_strength.value}.",
    ]
    if fusion.aligned_timeframes:
        values.append("Aligned timeframes: " + ", ".join(fusion.aligned_timeframes) + ".")
    if setup.supporting_evidence:
        values.extend(_sentence(item) for item in setup.supporting_evidence)
    if partial:
        values.append("Intelligence is partial.")
    return tuple(dict.fromkeys(values))


def _conflicting_evidence(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    setup: ExpertSetupClassificationSnapshot,
    partial: bool,
) -> tuple[str, ...]:
    values: list[str] = []
    if fusion.conflicting_timeframes:
        values.append("Conflicting timeframes: " + ", ".join(fusion.conflicting_timeframes) + ".")
    if fusion.weak_timeframes:
        values.append("Weak timeframes: " + ", ".join(fusion.weak_timeframes) + ".")
    if setup.conflicting_evidence:
        values.extend(_sentence(item) for item in setup.conflicting_evidence)
    if market_state.volatility_state is VolatilityState.VOLATILE:
        values.append("Volatility state is volatile.")
    if partial:
        values.append("Evidence incomplete.")
    return tuple(dict.fromkeys(values or ("No major conflict reported.",)))


def _risk_notes(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    setup: ExpertSetupClassificationSnapshot,
    partial: bool,
) -> tuple[str, ...]:
    notes: list[str] = []
    if partial:
        notes.append("Evidence incomplete.")
    if fusion.evidence_conflict is EvidenceConflict.MAJOR:
        notes.append("Higher timeframe disagreement is present.")
    if fusion.weak_timeframes:
        notes.append("Participation is uneven across timeframes.")
    if market_state.volatility_state is VolatilityState.VOLATILE:
        notes.append("Volatility is elevated.")
    if setup.setup_stability is SetupStability.UNSTABLE:
        notes.append("Setup stability is unstable.")
    if setup.setup_quality is SetupQuality.LOW:
        notes.append("Setup quality is low.")
    return tuple(dict.fromkeys(notes or ("No major caution from deterministic intelligence.",)))


def _quality(
    fusion: MultiTimeframeEvidenceSnapshot,
    market_state: MarketStateSnapshot,
    setup: ExpertSetupClassificationSnapshot,
    partial: bool,
) -> ExplanationQuality:
    if partial or fusion.evidence_completeness is not EvidenceCompleteness.COMPLETE:
        return ExplanationQuality.LOW
    if setup.setup_quality is SetupQuality.HIGH and market_state.evidence_quality is MarketEvidenceQuality.HIGH:
        return ExplanationQuality.HIGH
    if setup.setup_quality is SetupQuality.MEDIUM or market_state.evidence_quality is MarketEvidenceQuality.MEDIUM:
        return ExplanationQuality.MEDIUM
    return ExplanationQuality.LOW


def _is_partial(
    fusion: MultiTimeframeEvidenceSnapshot | None,
    market_state: MarketStateSnapshot | None,
    setup: ExpertSetupClassificationSnapshot | None,
    timestamp: datetime,
    maximum_source_age_seconds: int,
) -> bool:
    if fusion is None or market_state is None or setup is None:
        return True
    return (
        fusion.evidence_completeness is not EvidenceCompleteness.COMPLETE
        or market_state.evidence_quality in {MarketEvidenceQuality.LOW, MarketEvidenceQuality.INSUFFICIENT}
        or setup.setup_quality is SetupQuality.LOW
        or (timestamp - fusion.timestamp).total_seconds() > maximum_source_age_seconds
        or (timestamp - market_state.timestamp).total_seconds() > maximum_source_age_seconds
        or (timestamp - setup.timestamp).total_seconds() > maximum_source_age_seconds
    )


def _missing_reason(
    fusion: MultiTimeframeEvidenceSnapshot | None,
    market_state: MarketStateSnapshot | None,
    setup: ExpertSetupClassificationSnapshot | None,
) -> str:
    if fusion is None:
        return "multi-timeframe evidence"
    if market_state is None:
        return "market state"
    if setup is None:
        return "expert setup classification"
    return "intelligence"


def _sentence(value: str) -> str:
    normalized = str(value).strip().replace("_", " ")
    if not normalized:
        return "Evidence unavailable."
    return normalized if normalized.endswith(".") else normalized + "."


def _normalize_instrument(value: RuntimeInstrument | str) -> RuntimeInstrument:
    if isinstance(value, RuntimeInstrument):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        for instrument in RuntimeInstrument:
            if instrument.value == normalized or instrument.name == normalized:
                return instrument
    raise ValueError("instrument must be a RuntimeInstrument.")


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _fingerprint(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
