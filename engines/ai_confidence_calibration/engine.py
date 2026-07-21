"""
AI Confidence Calibration Engine V1.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.base_engine import BaseEngine
from core.events import (
    AI_CONFIDENCE_BLOCKED,
    AI_CONFIDENCE_CALIBRATED,
    AI_CONFIDENCE_FAILED,
    AI_CONFIDENCE_REDUCED,
    AI_CONFIDENCE_STATE_UPDATED,
)
from engines.ai_confidence_calibration.enums import (
    CalibrationDecision,
    ConfidenceBand,
    ConfidenceCalibrationLifecycle,
    EvidenceAlignment,
    EvidenceCategory,
)
from engines.ai_confidence_calibration.models import (
    ConfidenceCalibrationRequest,
    ConfidenceCalibrationResult,
    ConfidenceCalibrationSnapshot,
    ConfidenceEvidence,
    evidence_timestamp,
)
from engines.ai_reasoning.enums import AIMarketSummary
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context.enums import CPRPosition, CamarillaZone, EvidenceDirection, MarketBias, MarketPhase, VWAPPosition
from engines.market_context.models import MarketContextState
from engines.option_chain.enums import PositioningBias
from engines.option_chain.models import OptionChainState
from engines.price_action.enums import BreakDirection, MarketStructure, Trend
from engines.price_action.models import PriceActionState
from engines.strategy.enums import TradeDirection
from engines.vwap.levels import VWAPLevels


CATEGORY_WEIGHTS = {
    EvidenceCategory.PRICE_ACTION: 30,
    EvidenceCategory.OPTION_CHAIN: 30,
    EvidenceCategory.MARKET_CONTEXT: 15,
    EvidenceCategory.CPR_CAMARILLA: 10,
    EvidenceCategory.VWAP: 8,
    EvidenceCategory.SUPPORTING_INDICATORS: 7,
}

MAX_EVIDENCE_AGE_SECONDS = {
    EvidenceCategory.PRICE_ACTION: 300,
    EvidenceCategory.OPTION_CHAIN: 180,
    EvidenceCategory.MARKET_CONTEXT: 900,
    EvidenceCategory.CPR_CAMARILLA: 86400,
    EvidenceCategory.VWAP: 300,
    EvidenceCategory.SUPPORTING_INDICATORS: 300,
}

_ALIGNMENT_PERCENT = {
    EvidenceAlignment.SUPPORTS: 1.0,
    EvidenceAlignment.NEUTRAL: 0.0,
    EvidenceAlignment.MISSING: 0.0,
    EvidenceAlignment.STALE: -0.5,
    EvidenceAlignment.CONFLICTS: -1.0,
    EvidenceAlignment.INVALID: -1.0,
}


@dataclass(frozen=True, slots=True)
class _ClassifiedEvidence:
    category: EvidenceCategory
    alignment: EvidenceAlignment
    reason_code: str
    explanation: str
    source_timestamp: object
    age_seconds: float | None
    direction: TradeDirection | None = None


class AIConfidenceCalibrationEngine(BaseEngine):
    """
    Deterministic confidence calibration for existing AI and strategy decisions.

    The engine reads immutable evidence only. It never creates a direction,
    evaluates risk, prepares execution, mutates positions, calls a broker, or
    calls an external service.
    """

    def __init__(self, event_bus, symbol: str, timeframe: str):
        super().__init__(event_bus)
        self._symbol = _normalize_symbol(symbol)
        self._timeframe = _normalize_timeframe(timeframe)
        self._lifecycle_state = ConfidenceCalibrationLifecycle.CREATED
        self._results: dict[str, ConfidenceCalibrationResult] = {}
        self._fingerprints: dict[str, str] = {}
        self._last_result: ConfidenceCalibrationResult | None = None
        self._calibration_count = 0
        self._trusted_count = 0
        self._reduced_count = 0
        self._blocked_count = 0

    def start(self) -> ConfidenceCalibrationSnapshot:
        if self._lifecycle_state is ConfidenceCalibrationLifecycle.CREATED:
            self._lifecycle_state = ConfidenceCalibrationLifecycle.READY
            self._publish_state()
        return self.snapshot()

    def calibrate(self, request: ConfidenceCalibrationRequest) -> ConfidenceCalibrationResult:
        if self._lifecycle_state is ConfidenceCalibrationLifecycle.STOPPED:
            raise RuntimeError("Confidence calibration is stopped.")
        if self._lifecycle_state is ConfidenceCalibrationLifecycle.FAILED:
            raise RuntimeError("Confidence calibration is failed.")
        if self._lifecycle_state is ConfidenceCalibrationLifecycle.CREATED:
            raise RuntimeError("Confidence calibration engine must be started.")
        if not isinstance(request, ConfidenceCalibrationRequest):
            raise TypeError("request must be ConfidenceCalibrationRequest")
        self._validate_request_context(request)
        fingerprint = request.fingerprint()
        stored = self._results.get(request.calibration_id)
        if stored is not None:
            if self._fingerprints[request.calibration_id] != fingerprint:
                raise ValueError("calibration_id already exists for different request")
            return stored

        try:
            result = self._calibrate(request)
        except Exception as exc:
            if isinstance(exc, (TypeError, ValueError, RuntimeError)):
                raise
            self._lifecycle_state = ConfidenceCalibrationLifecycle.FAILED
            self._event_bus.publish(AI_CONFIDENCE_FAILED, self.snapshot())
            self._publish_state()
            raise

        self._results[request.calibration_id] = result
        self._fingerprints[request.calibration_id] = fingerprint
        self._last_result = result
        self._data = result
        self._calibration_count += 1
        if result.calibration_decision is CalibrationDecision.BLOCK:
            self._blocked_count += 1
        elif result.calibration_decision is CalibrationDecision.REDUCE:
            self._reduced_count += 1
        else:
            self._trusted_count += 1
        if self._lifecycle_state is ConfidenceCalibrationLifecycle.READY:
            self._lifecycle_state = ConfidenceCalibrationLifecycle.ACTIVE
        self._event_bus.publish(AI_CONFIDENCE_CALIBRATED, result)
        if result.calibration_decision is CalibrationDecision.BLOCK:
            self._event_bus.publish(AI_CONFIDENCE_BLOCKED, result)
        elif result.calibration_decision is CalibrationDecision.REDUCE:
            self._event_bus.publish(AI_CONFIDENCE_REDUCED, result)
        self._publish_state()
        return result

    def get_result(self, calibration_id: str) -> ConfidenceCalibrationResult | None:
        if not isinstance(calibration_id, str) or not calibration_id.strip():
            raise ValueError("calibration_id must be non-empty text")
        return self._results.get(calibration_id.strip())

    def stop(self) -> ConfidenceCalibrationSnapshot:
        if self._lifecycle_state in {
            ConfidenceCalibrationLifecycle.CREATED,
            ConfidenceCalibrationLifecycle.READY,
            ConfidenceCalibrationLifecycle.ACTIVE,
        }:
            self._lifecycle_state = ConfidenceCalibrationLifecycle.STOPPED
            self._publish_state()
        return self.snapshot()

    def reset(self) -> ConfidenceCalibrationSnapshot:
        self._results.clear()
        self._fingerprints.clear()
        self._last_result = None
        self._data = None
        self._calibration_count = 0
        self._trusted_count = 0
        self._reduced_count = 0
        self._blocked_count = 0
        self._lifecycle_state = ConfidenceCalibrationLifecycle.READY
        self._publish_state()
        return self.snapshot()

    def snapshot(self) -> ConfidenceCalibrationSnapshot:
        return ConfidenceCalibrationSnapshot(
            enabled=True,
            lifecycle_state=self._lifecycle_state,
            calibration_count=self._calibration_count,
            trusted_count=self._trusted_count,
            reduced_count=self._reduced_count,
            blocked_count=self._blocked_count,
            last_result=self._last_result,
        )

    def _calibrate(self, request: ConfidenceCalibrationRequest) -> ConfidenceCalibrationResult:
        decision_direction = request.strategy_decision.direction
        ai_direction = _ai_direction(request.ai_reasoning.market_summary)
        classified = (
            self._classify_price_action(request.price_action, decision_direction, request),
            self._classify_option_chain(request.option_chain, decision_direction, request),
            self._classify_market_context(request.market_context, decision_direction, request),
            self._classify_cpr_camarilla(request.cpr, request.camarilla, decision_direction, request),
            self._classify_vwap(request.vwap, decision_direction, request),
            self._classify_supporting_indicators(request.supporting_indicators, decision_direction, request),
        )
        evidence = tuple(self._to_evidence(item) for item in classified)
        raw_score = _clamp(50 + sum(item.contribution for item in evidence))
        penalties, blocked_reasons = self._penalties(classified, ai_direction, decision_direction)
        final_score = _clamp(raw_score - penalties)
        blocked = bool(blocked_reasons)
        band = ConfidenceBand.BLOCKED if blocked else _band(final_score)
        decision = CalibrationDecision.BLOCK if blocked else (CalibrationDecision.REDUCE if final_score < 45 else CalibrationDecision.TRUST)
        primary_reason = blocked_reasons[0] if blocked_reasons else f"confidence_{decision.value}"
        return ConfidenceCalibrationResult(
            calibration_id=request.calibration_id,
            timestamp=request.timestamp,
            instrument=request.instrument,
            direction=decision_direction,
            raw_score=raw_score,
            penalty_score=penalties,
            final_score=final_score,
            confidence_band=band,
            calibration_decision=decision,
            primary_reason=primary_reason,
            evidence=evidence,
            supporting_categories=_categories(evidence, EvidenceAlignment.SUPPORTS),
            conflicting_categories=_categories(evidence, EvidenceAlignment.CONFLICTS),
            missing_categories=_categories(evidence, EvidenceAlignment.MISSING),
            stale_categories=_categories(evidence, EvidenceAlignment.STALE),
            invalid_categories=_categories(evidence, EvidenceAlignment.INVALID),
            blocked_reasons=tuple(blocked_reasons),
            correlation_id=request.correlation_id,
        )

    def _validate_request_context(self, request: ConfidenceCalibrationRequest) -> None:
        if request.instrument.value != self._symbol:
            raise ValueError("Confidence request instrument does not match engine context.")
        if _normalize_symbol(request.ai_reasoning.symbol) != self._symbol:
            raise ValueError("AI reasoning instrument does not match engine context.")
        if _normalize_symbol(request.strategy_decision.symbol) != self._symbol:
            raise ValueError("Strategy decision instrument does not match engine context.")
        if _normalize_timeframe(request.ai_reasoning.timeframe) != self._timeframe:
            raise ValueError("AI reasoning timeframe does not match engine context.")
        if _normalize_timeframe(request.strategy_decision.timeframe) != self._timeframe:
            raise ValueError("Strategy decision timeframe does not match engine context.")

    def _to_evidence(self, item: _ClassifiedEvidence) -> ConfidenceEvidence:
        maximum = CATEGORY_WEIGHTS[item.category]
        return ConfidenceEvidence(
            category=item.category,
            alignment=item.alignment,
            maximum_weight=maximum,
            contribution=round(maximum * _ALIGNMENT_PERCENT[item.alignment], 2),
            reason_code=item.reason_code,
            explanation=item.explanation,
            source_timestamp=item.source_timestamp,
            age_seconds=item.age_seconds,
        )

    def _classify_price_action(self, state, decision: TradeDirection, request: ConfidenceCalibrationRequest) -> _ClassifiedEvidence:
        category = EvidenceCategory.PRICE_ACTION
        missing = self._missing(category, request)
        if state is None:
            return missing
        if not isinstance(state, PriceActionState):
            return self._invalid(category, request, "invalid_price_action", "Price Action result is invalid.")
        stale = self._stale(category, state, request)
        if stale is not None:
            return stale
        direction = _price_action_direction(state)
        return self._directional(category, direction, decision, request, "price_action")

    def _classify_option_chain(self, state, decision: TradeDirection, request: ConfidenceCalibrationRequest) -> _ClassifiedEvidence:
        category = EvidenceCategory.OPTION_CHAIN
        if state is None:
            return self._missing(category, request)
        if not isinstance(state, OptionChainState):
            return self._invalid(category, request, "invalid_option_chain", "Option Chain result is invalid.")
        stale = self._stale(category, state, request)
        if stale is not None:
            return stale
        direction = _option_chain_direction(state.positioning_bias)
        return self._directional(category, direction, decision, request, "option_chain")

    def _classify_market_context(self, state, decision: TradeDirection, request: ConfidenceCalibrationRequest) -> _ClassifiedEvidence:
        category = EvidenceCategory.MARKET_CONTEXT
        if state is None:
            return self._missing(category, request)
        if not isinstance(state, MarketContextState):
            return self._invalid(category, request, "invalid_market_context", "Market Context result is invalid.")
        stale = self._stale(category, state, request)
        if stale is not None:
            return stale
        direction = _market_context_direction(state)
        return self._directional(category, direction, decision, request, "market_context")

    def _classify_cpr_camarilla(self, cpr, camarilla, decision: TradeDirection, request: ConfidenceCalibrationRequest) -> _ClassifiedEvidence:
        category = EvidenceCategory.CPR_CAMARILLA
        if cpr is None and camarilla is None:
            return self._missing(category, request)
        if cpr is not None and not isinstance(cpr, CPRLevels):
            return self._invalid(category, request, "invalid_cpr", "CPR result is invalid.")
        if camarilla is not None and not isinstance(camarilla, CamarillaLevels):
            return self._invalid(category, request, "invalid_camarilla", "Camarilla result is invalid.")
        stale_items = tuple(item for item in (cpr, camarilla) if self._stale(category, item, request) is not None)
        if stale_items:
            return self._stale(category, stale_items[0], request)
        price = getattr(request.market_context, "current_price", None)
        cpr_alignment = _alignment_from_direction(_cpr_direction(cpr, price), decision) if cpr is not None else EvidenceAlignment.MISSING
        camarilla_alignment = (
            _alignment_from_direction(_camarilla_direction(camarilla, price), decision)
            if camarilla is not None
            else EvidenceAlignment.MISSING
        )
        alignment = _combine_cpr_camarilla(cpr_alignment, camarilla_alignment)
        return self._classified(category, alignment, request, f"cpr_camarilla_{alignment.value}", "CPR and Camarilla evidence was classified.")

    def _classify_vwap(self, state, decision: TradeDirection, request: ConfidenceCalibrationRequest) -> _ClassifiedEvidence:
        category = EvidenceCategory.VWAP
        if state is None:
            return self._missing(category, request)
        if not isinstance(state, VWAPLevels):
            return self._invalid(category, request, "invalid_vwap", "VWAP result is invalid.")
        stale = self._stale(category, state, request)
        if stale is not None:
            return stale
        price = getattr(request.market_context, "current_price", None)
        direction = _vwap_direction(state, price)
        return self._directional(category, direction, decision, request, "vwap")

    def _classify_supporting_indicators(
        self,
        indicators: tuple[object, ...],
        decision: TradeDirection,
        request: ConfidenceCalibrationRequest,
    ) -> _ClassifiedEvidence:
        category = EvidenceCategory.SUPPORTING_INDICATORS
        if not indicators:
            return self._missing(category, request)
        stale_items = tuple(item for item in indicators if self._stale(category, item, request) is not None)
        if stale_items:
            return self._stale(category, stale_items[0], request)
        alignments = tuple(_indicator_alignment(item, decision) for item in indicators)
        supports = alignments.count(EvidenceAlignment.SUPPORTS)
        conflicts = alignments.count(EvidenceAlignment.CONFLICTS)
        if supports > conflicts:
            alignment = EvidenceAlignment.SUPPORTS
        elif conflicts > supports:
            alignment = EvidenceAlignment.CONFLICTS
        else:
            alignment = EvidenceAlignment.NEUTRAL
        return self._classified(category, alignment, request, f"supporting_indicators_{alignment.value}", "Supporting indicators were classified.")

    def _directional(
        self,
        category: EvidenceCategory,
        evidence_direction: TradeDirection | None,
        decision: TradeDirection,
        request: ConfidenceCalibrationRequest,
        prefix: str,
    ) -> _ClassifiedEvidence:
        alignment = _alignment_from_direction(evidence_direction, decision)
        return self._classified(
            category,
            alignment,
            request,
            f"{prefix}_{alignment.value}",
            f"{category.value} evidence {alignment.value}.",
            evidence_direction,
        )

    def _classified(
        self,
        category: EvidenceCategory,
        alignment: EvidenceAlignment,
        request: ConfidenceCalibrationRequest,
        reason_code: str,
        explanation: str,
        direction: TradeDirection | None = None,
    ) -> _ClassifiedEvidence:
        value = _evidence_value(category, request)
        timestamp, age = self._age(category, value, request)
        return _ClassifiedEvidence(category, alignment, reason_code, explanation, timestamp, age, direction)

    def _missing(self, category: EvidenceCategory, request: ConfidenceCalibrationRequest) -> _ClassifiedEvidence:
        return _ClassifiedEvidence(category, EvidenceAlignment.MISSING, f"{category.value}_missing", f"{category.value} evidence is missing.", None, None)

    def _invalid(
        self,
        category: EvidenceCategory,
        request: ConfidenceCalibrationRequest,
        reason_code: str,
        explanation: str,
    ) -> _ClassifiedEvidence:
        return _ClassifiedEvidence(category, EvidenceAlignment.INVALID, reason_code, explanation, None, None)

    def _stale(self, category: EvidenceCategory, value: object, request: ConfidenceCalibrationRequest) -> _ClassifiedEvidence | None:
        timestamp, age = self._age(category, value, request)
        if age is not None and age > MAX_EVIDENCE_AGE_SECONDS[category]:
            return _ClassifiedEvidence(category, EvidenceAlignment.STALE, f"{category.value}_stale", f"{category.value} evidence is stale.", timestamp, age)
        return None

    def _age(self, category: EvidenceCategory, value: object, request: ConfidenceCalibrationRequest):
        timestamp = evidence_timestamp(value, request.timestamp)
        if timestamp is None:
            return None, None
        age = (request.timestamp - timestamp).total_seconds()
        if age < 0:
            raise ValueError(f"{category.value} timestamp cannot be in the future")
        return timestamp, age

    def _penalties(
        self,
        classified: tuple[_ClassifiedEvidence, ...],
        ai_direction: TradeDirection,
        decision_direction: TradeDirection,
    ) -> tuple[float, list[str]]:
        by_category = {item.category: item for item in classified}
        penalty = 0.0
        blocked: list[str] = []
        price_action = by_category[EvidenceCategory.PRICE_ACTION]
        option_chain = by_category[EvidenceCategory.OPTION_CHAIN]
        if (
            price_action.direction in {TradeDirection.BULLISH, TradeDirection.BEARISH}
            and option_chain.direction in {TradeDirection.BULLISH, TradeDirection.BEARISH}
            and price_action.direction is not option_chain.direction
        ):
            penalty += 35
            blocked.append("primary_evidence_conflict")
        for category in (EvidenceCategory.PRICE_ACTION, EvidenceCategory.OPTION_CHAIN):
            item = by_category[category]
            if item.alignment is EvidenceAlignment.MISSING:
                penalty += 20
            elif item.alignment is EvidenceAlignment.STALE:
                penalty += 15
            elif item.alignment is EvidenceAlignment.INVALID:
                blocked.append(f"{category.value}_invalid")
        if price_action.alignment is EvidenceAlignment.MISSING and option_chain.alignment is EvidenceAlignment.MISSING:
            blocked.append("primary_evidence_missing")
        if price_action.alignment is EvidenceAlignment.STALE and option_chain.alignment is EvidenceAlignment.STALE:
            blocked.append("primary_evidence_stale")
        if ai_direction is not decision_direction:
            penalty += 25
            blocked.append("ai_strategy_direction_mismatch")
        return penalty, blocked

    def _publish_state(self) -> None:
        self._event_bus.publish(AI_CONFIDENCE_STATE_UPDATED, self.snapshot())


def _evidence_value(category: EvidenceCategory, request: ConfidenceCalibrationRequest):
    return {
        EvidenceCategory.PRICE_ACTION: request.price_action,
        EvidenceCategory.OPTION_CHAIN: request.option_chain,
        EvidenceCategory.MARKET_CONTEXT: request.market_context,
        EvidenceCategory.CPR_CAMARILLA: request.cpr or request.camarilla,
        EvidenceCategory.VWAP: request.vwap,
        EvidenceCategory.SUPPORTING_INDICATORS: request.supporting_indicators[0] if request.supporting_indicators else None,
    }[category]


def _categories(evidence: tuple[ConfidenceEvidence, ...], alignment: EvidenceAlignment) -> tuple[EvidenceCategory, ...]:
    return tuple(item.category for item in evidence if item.alignment is alignment)


def _alignment_from_direction(evidence_direction: TradeDirection | None, decision: TradeDirection) -> EvidenceAlignment:
    if evidence_direction is None or evidence_direction is TradeDirection.NONE or decision is TradeDirection.NONE:
        return EvidenceAlignment.NEUTRAL
    if evidence_direction is decision:
        return EvidenceAlignment.SUPPORTS
    return EvidenceAlignment.CONFLICTS


def _ai_direction(summary: AIMarketSummary) -> TradeDirection:
    if summary is AIMarketSummary.BULLISH:
        return TradeDirection.BULLISH
    if summary is AIMarketSummary.BEARISH:
        return TradeDirection.BEARISH
    return TradeDirection.NONE


def _price_action_direction(state: PriceActionState) -> TradeDirection | None:
    if state.trend is Trend.BULLISH or state.market_structure is MarketStructure.BULLISH or state.bos_direction is BreakDirection.BULLISH:
        return TradeDirection.BULLISH
    if state.trend is Trend.BEARISH or state.market_structure is MarketStructure.BEARISH or state.bos_direction is BreakDirection.BEARISH:
        return TradeDirection.BEARISH
    return None


def _option_chain_direction(bias: PositioningBias) -> TradeDirection | None:
    if bias is PositioningBias.BULLISH:
        return TradeDirection.BULLISH
    if bias is PositioningBias.BEARISH:
        return TradeDirection.BEARISH
    return None


def _market_context_direction(state: MarketContextState) -> TradeDirection | None:
    if state.market_bias is MarketBias.BULLISH or state.market_phase in {MarketPhase.TRENDING_UP, MarketPhase.BREAKOUT_UP, MarketPhase.REVERSAL_UP}:
        return TradeDirection.BULLISH
    if state.market_bias is MarketBias.BEARISH or state.market_phase in {MarketPhase.TRENDING_DOWN, MarketPhase.BREAKOUT_DOWN, MarketPhase.REVERSAL_DOWN}:
        return TradeDirection.BEARISH
    return None


def _cpr_direction(cpr: CPRLevels | None, price: object) -> TradeDirection | None:
    if cpr is None or not isinstance(price, (int, float)):
        return None
    if price > cpr.tc:
        return TradeDirection.BULLISH
    if price < cpr.bc:
        return TradeDirection.BEARISH
    return None


def _camarilla_direction(camarilla: CamarillaLevels | None, price: object) -> TradeDirection | None:
    if camarilla is None or not isinstance(price, (int, float)):
        return None
    if price > camarilla.h3:
        return TradeDirection.BULLISH
    if price < camarilla.l3:
        return TradeDirection.BEARISH
    return None


def _combine_cpr_camarilla(cpr: EvidenceAlignment, camarilla: EvidenceAlignment) -> EvidenceAlignment:
    alignments = (cpr, camarilla)
    if alignments.count(EvidenceAlignment.SUPPORTS) == 2:
        return EvidenceAlignment.SUPPORTS
    if EvidenceAlignment.SUPPORTS in alignments and all(item in {EvidenceAlignment.SUPPORTS, EvidenceAlignment.NEUTRAL, EvidenceAlignment.MISSING} for item in alignments):
        return EvidenceAlignment.SUPPORTS
    if EvidenceAlignment.SUPPORTS in alignments and EvidenceAlignment.CONFLICTS in alignments:
        return EvidenceAlignment.NEUTRAL
    if EvidenceAlignment.CONFLICTS in alignments:
        return EvidenceAlignment.CONFLICTS
    if alignments.count(EvidenceAlignment.MISSING) == 2:
        return EvidenceAlignment.MISSING
    return EvidenceAlignment.NEUTRAL


def _vwap_direction(state, price: object) -> TradeDirection | None:
    if hasattr(state, "symbol") and not hasattr(state, "vwap"):
        return None
    if isinstance(price, (int, float)):
        if price > state.vwap:
            return TradeDirection.BULLISH
        if price < state.vwap:
            return TradeDirection.BEARISH
    position = getattr(state, "vwap_position", None)
    if position is VWAPPosition.ABOVE:
        return TradeDirection.BULLISH
    if position is VWAPPosition.BELOW:
        return TradeDirection.BEARISH
    return None


def _indicator_alignment(item: object, decision: TradeDirection) -> EvidenceAlignment:
    raw = getattr(item, "alignment", getattr(item, "direction", None))
    value = raw.value if hasattr(raw, "value") else str(raw).strip().lower() if raw is not None else ""
    if value in {"supports", "support", "bullish" if decision is TradeDirection.BULLISH else "bearish"}:
        return EvidenceAlignment.SUPPORTS
    if value in {"conflicts", "conflict", "bearish" if decision is TradeDirection.BULLISH else "bullish"}:
        return EvidenceAlignment.CONFLICTS
    return EvidenceAlignment.NEUTRAL


def _band(score: float) -> ConfidenceBand:
    if score <= 24:
        return ConfidenceBand.VERY_LOW
    if score <= 44:
        return ConfidenceBand.LOW
    if score <= 64:
        return ConfidenceBand.MODERATE
    if score <= 84:
        return ConfidenceBand.HIGH
    return ConfidenceBand.VERY_HIGH


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _normalize_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("symbol must be text")
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol cannot be empty")
    return normalized


def _normalize_timeframe(timeframe: str) -> str:
    if not isinstance(timeframe, str):
        raise ValueError("timeframe must be text")
    normalized = timeframe.strip()
    if not normalized:
        raise ValueError("timeframe cannot be empty")
    return normalized
