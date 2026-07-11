"""
Stateless AI Reasoning Engine V1 calculations.
"""

from engines.ai_reasoning.enums import (
    AgreementSummary,
    AIMarketSummary,
    ConflictSummary,
    ReasoningConfidence,
    TradingSuitability,
)
from engines.ai_reasoning.models import AIReasoningState
from engines.market_context.enums import AgreementState, ContextStrength, EvidenceDirection, MarketBias
from engines.market_context.models import MarketContextState


class AIReasoningCalculator:
    """
    Converts deterministic market context into deterministic reasoning.

    The calculator consumes only MarketContextState. It does not calculate
    indicators, call models, access the network, fetch broker data, create
    orders, persist data, or execute trades.
    """

    @staticmethod
    def calculate(context: MarketContextState) -> AIReasoningState:
        market_summary = AIReasoningCalculator._market_summary(context.market_bias)
        confidence = AIReasoningCalculator._confidence(context.context_strength)
        agreement_summary = AIReasoningCalculator._agreement_summary(context.agreement)
        conflict_summary = AIReasoningCalculator._conflict_summary(context)
        trading_suitability = AIReasoningCalculator._trading_suitability(
            context,
            confidence,
            conflict_summary,
        )
        explanation = AIReasoningCalculator._explanation(
            context,
            market_summary,
            confidence,
            agreement_summary,
            conflict_summary,
            trading_suitability,
        )

        return AIReasoningState(
            symbol=context.symbol,
            timeframe=context.timeframe,
            timestamp=context.timestamp,
            market_summary=market_summary,
            confidence=confidence,
            agreement_summary=agreement_summary,
            conflict_summary=conflict_summary,
            trading_suitability=trading_suitability,
            missing_information=context.missing_sources,
            explanation=explanation,
        )

    @staticmethod
    def _market_summary(market_bias: MarketBias) -> AIMarketSummary:
        mapping = {
            MarketBias.BULLISH: AIMarketSummary.BULLISH,
            MarketBias.BEARISH: AIMarketSummary.BEARISH,
            MarketBias.NEUTRAL: AIMarketSummary.NEUTRAL,
            MarketBias.MIXED: AIMarketSummary.MIXED,
            MarketBias.UNKNOWN: AIMarketSummary.INSUFFICIENT,
        }
        return mapping[market_bias]

    @staticmethod
    def _confidence(strength: ContextStrength) -> ReasoningConfidence:
        mapping = {
            ContextStrength.STRONG: ReasoningConfidence.HIGH,
            ContextStrength.MODERATE: ReasoningConfidence.MEDIUM,
            ContextStrength.WEAK: ReasoningConfidence.LOW,
            ContextStrength.INSUFFICIENT: ReasoningConfidence.INSUFFICIENT,
        }
        return mapping[strength]

    @staticmethod
    def _agreement_summary(agreement: AgreementState) -> AgreementSummary:
        mapping = {
            AgreementState.ALIGNED: AgreementSummary.ALIGNED,
            AgreementState.CONFLICTED: AgreementSummary.CONFLICTED,
            AgreementState.PARTIAL: AgreementSummary.PARTIAL,
            AgreementState.INSUFFICIENT: AgreementSummary.INSUFFICIENT,
        }
        return mapping[agreement]

    @staticmethod
    def _conflict_summary(context: MarketContextState) -> ConflictSummary:
        if context.agreement is AgreementState.INSUFFICIENT:
            return ConflictSummary.INSUFFICIENT
        if context.agreement is AgreementState.CONFLICTED:
            return ConflictSummary.PRIMARY_CONFLICT
        if context.bullish_evidence_count > 0 and context.bearish_evidence_count > 0:
            return ConflictSummary.SECONDARY_CONFLICT
        if context.mixed_evidence_count > 0 or context.market_bias is MarketBias.MIXED:
            return ConflictSummary.MIXED_SIGNALS
        return ConflictSummary.NONE

    @staticmethod
    def _trading_suitability(
        context: MarketContextState,
        confidence: ReasoningConfidence,
        conflict_summary: ConflictSummary,
    ) -> TradingSuitability:
        if confidence is ReasoningConfidence.INSUFFICIENT:
            return TradingSuitability.INSUFFICIENT
        if conflict_summary in {ConflictSummary.PRIMARY_CONFLICT, ConflictSummary.SECONDARY_CONFLICT}:
            return TradingSuitability.UNSUITABLE
        if context.market_bias in {MarketBias.NEUTRAL, MarketBias.MIXED, MarketBias.UNKNOWN}:
            return TradingSuitability.WATCHLIST
        if confidence is ReasoningConfidence.HIGH:
            return TradingSuitability.SUITABLE
        return TradingSuitability.WATCHLIST

    @staticmethod
    def _explanation(
        context: MarketContextState,
        market_summary: AIMarketSummary,
        confidence: ReasoningConfidence,
        agreement_summary: AgreementSummary,
        conflict_summary: ConflictSummary,
        trading_suitability: TradingSuitability,
    ) -> str:
        evidence_text = AIReasoningCalculator._evidence_text(context)
        missing_text = AIReasoningCalculator._missing_text(context.missing_sources)
        return (
            f"{context.symbol} {context.timeframe} context is {market_summary.value} "
            f"with {confidence.value} confidence. "
            f"Primary agreement is {agreement_summary.value}; conflict status is {conflict_summary.value}. "
            f"Trading suitability is {trading_suitability.value}. "
            f"Market phase is {context.market_phase.value} and context strength is "
            f"{context.context_strength.value}. "
            f"Evidence: {evidence_text}. "
            f"Missing information: {missing_text}."
        )

    @staticmethod
    def _evidence_text(context: MarketContextState) -> str:
        if not context.evidence:
            return "none"
        return ", ".join(
            f"{item.source}={item.direction.value}"
            for item in context.evidence
            if item.direction is not EvidenceDirection.UNKNOWN
        ) or "none"

    @staticmethod
    def _missing_text(missing_sources: tuple[str, ...]) -> str:
        if not missing_sources:
            return "none"
        return ", ".join(missing_sources)
