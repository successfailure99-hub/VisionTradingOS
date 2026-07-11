"""
Stateless Strategy Engine V1 calculations.
"""

from engines.ai_reasoning.enums import (
    AgreementSummary,
    AIMarketSummary,
    ConflictSummary,
    ReasoningConfidence,
    TradingSuitability,
)
from engines.market_context.enums import CamarillaZone, MarketBias, MarketPhase
from engines.strategy.enums import (
    BlockReason,
    EntryReference,
    SetupQuality,
    StopReference,
    StrategyDecision,
    TargetReference,
    TradeDirection,
)
from engines.strategy.models import StrategyDecisionState, StrategySnapshot


class StrategyCalculator:
    """
    Converts AI reasoning and market context into a strategy decision.

    V1 is proposal-only. It does not place orders, select option
    contracts, size positions, calculate monetary risk, fetch data, call
    models, use networking, persist state, or make guaranteed-profit
    claims.
    """

    BREAK_PHASES = {
        MarketPhase.BREAKOUT_UP,
        MarketPhase.BREAKOUT_DOWN,
        MarketPhase.REVERSAL_UP,
        MarketPhase.REVERSAL_DOWN,
    }
    TREND_PHASES = {MarketPhase.TRENDING_UP, MarketPhase.TRENDING_DOWN}

    @staticmethod
    def calculate(snapshot: StrategySnapshot) -> StrategyDecisionState:
        ai = snapshot.ai_reasoning
        context = snapshot.market_context

        block_reason = StrategyCalculator._block_reason(snapshot)
        if block_reason is not BlockReason.NONE:
            return StrategyCalculator._rejected(snapshot, block_reason)

        direction = StrategyCalculator._direction(ai.market_summary)
        entry_reference = StrategyCalculator._entry_reference(context.market_phase)
        if entry_reference is EntryReference.NONE:
            return StrategyCalculator._rejected(snapshot, BlockReason.UNSUITABLE_CONTEXT)

        stop_reference = StrategyCalculator._stop_reference(context.market_phase)
        target_reference = StrategyCalculator._target_reference(snapshot)
        setup_quality = StrategyCalculator._setup_quality(snapshot)
        rationale = StrategyCalculator._rationale(
            snapshot,
            block_reason=BlockReason.NONE,
            entry_reference=entry_reference,
            target_reference=target_reference,
        )

        return StrategyDecisionState(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            timestamp=snapshot.timestamp,
            decision=StrategyDecision.TRADE_ELIGIBLE,
            direction=direction,
            setup_quality=setup_quality,
            entry_reference=entry_reference,
            stop_reference=stop_reference,
            target_reference=target_reference,
            block_reason=BlockReason.NONE,
            market_bias=context.market_bias,
            market_phase=context.market_phase,
            confidence=ai.confidence,
            trading_suitability=ai.trading_suitability,
            rationale=rationale,
        )

    @staticmethod
    def _block_reason(snapshot: StrategySnapshot) -> BlockReason:
        ai = snapshot.ai_reasoning
        context = snapshot.market_context

        if (
            ai.market_summary is AIMarketSummary.INSUFFICIENT
            or ai.confidence is ReasoningConfidence.INSUFFICIENT
            or ai.agreement_summary is AgreementSummary.INSUFFICIENT
            or ai.trading_suitability is TradingSuitability.INSUFFICIENT
        ):
            return BlockReason.INSUFFICIENT_CONTEXT

        if "price_action" in context.missing_sources or "option_chain" in context.missing_sources:
            return BlockReason.MISSING_PRIMARY_DATA

        if ai.conflict_summary is ConflictSummary.PRIMARY_CONFLICT or ai.agreement_summary is AgreementSummary.CONFLICTED:
            return BlockReason.PRIMARY_CONFLICT

        if ai.conflict_summary is ConflictSummary.SECONDARY_CONFLICT:
            return BlockReason.SECONDARY_CONFLICT

        if ai.trading_suitability is TradingSuitability.UNSUITABLE:
            return BlockReason.UNSUITABLE_CONTEXT

        if ai.confidence is ReasoningConfidence.LOW:
            return BlockReason.LOW_CONFIDENCE

        if context.market_bias is MarketBias.NEUTRAL:
            return BlockReason.NEUTRAL_BIAS
        if context.market_bias is MarketBias.MIXED:
            return BlockReason.MIXED_BIAS
        if context.market_bias is MarketBias.UNKNOWN:
            return BlockReason.UNKNOWN_BIAS

        if not StrategyCalculator._direction_matches(ai.market_summary, context.market_bias):
            return BlockReason.DIRECTION_MISMATCH

        if not StrategyCalculator._eligible(ai):
            return BlockReason.UNSUITABLE_CONTEXT

        return BlockReason.NONE

    @staticmethod
    def _eligible(ai) -> bool:
        return (
            ai.market_summary in {AIMarketSummary.BULLISH, AIMarketSummary.BEARISH}
            and ai.confidence in {ReasoningConfidence.HIGH, ReasoningConfidence.MEDIUM}
            and ai.trading_suitability in {TradingSuitability.SUITABLE, TradingSuitability.WATCHLIST}
            and ai.agreement_summary in {AgreementSummary.ALIGNED, AgreementSummary.PARTIAL}
            and ai.conflict_summary in {ConflictSummary.NONE, ConflictSummary.MIXED_SIGNALS}
        )

    @staticmethod
    def _direction_matches(summary: AIMarketSummary, bias: MarketBias) -> bool:
        return (
            summary is AIMarketSummary.BULLISH
            and bias is MarketBias.BULLISH
        ) or (
            summary is AIMarketSummary.BEARISH
            and bias is MarketBias.BEARISH
        )

    @staticmethod
    def _direction(summary: AIMarketSummary) -> TradeDirection:
        if summary is AIMarketSummary.BULLISH:
            return TradeDirection.BULLISH
        if summary is AIMarketSummary.BEARISH:
            return TradeDirection.BEARISH
        return TradeDirection.NONE

    @staticmethod
    def _setup_quality(snapshot: StrategySnapshot) -> SetupQuality:
        ai = snapshot.ai_reasoning
        if (
            ai.confidence is ReasoningConfidence.HIGH
            and ai.trading_suitability is TradingSuitability.SUITABLE
            and ai.agreement_summary is AgreementSummary.ALIGNED
            and ai.conflict_summary is ConflictSummary.NONE
        ):
            return SetupQuality.HIGH
        return SetupQuality.MEDIUM

    @staticmethod
    def _entry_reference(phase: MarketPhase) -> EntryReference:
        if phase in StrategyCalculator.BREAK_PHASES:
            return EntryReference.STRUCTURE_BREAK_RETEST
        if phase in StrategyCalculator.TREND_PHASES:
            return EntryReference.PRICE_ACTION_RETEST
        return EntryReference.NONE

    @staticmethod
    def _stop_reference(phase: MarketPhase) -> StopReference:
        if phase in StrategyCalculator.BREAK_PHASES:
            return StopReference.BROKEN_STRUCTURE
        if phase in StrategyCalculator.TREND_PHASES:
            return StopReference.LATEST_SWING
        return StopReference.NONE

    @staticmethod
    def _target_reference(snapshot: StrategySnapshot) -> TargetReference:
        context = snapshot.market_context
        if context.camarilla_zone not in {CamarillaZone.UNAVAILABLE, CamarillaZone.L3_TO_H3}:
            return TargetReference.CAMARILLA_LEVEL
        if "option_chain" not in context.missing_sources:
            return TargetReference.OPTION_OI_LEVEL
        return TargetReference.NEXT_STRUCTURE

    @staticmethod
    def _rejected(snapshot: StrategySnapshot, block_reason: BlockReason) -> StrategyDecisionState:
        return StrategyDecisionState(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            timestamp=snapshot.timestamp,
            decision=StrategyDecision.NO_TRADE,
            direction=TradeDirection.NONE,
            setup_quality=SetupQuality.REJECTED,
            entry_reference=EntryReference.NONE,
            stop_reference=StopReference.NONE,
            target_reference=TargetReference.NONE,
            block_reason=block_reason,
            market_bias=snapshot.market_context.market_bias,
            market_phase=snapshot.market_context.market_phase,
            confidence=snapshot.ai_reasoning.confidence,
            trading_suitability=snapshot.ai_reasoning.trading_suitability,
            rationale=StrategyCalculator._rationale(snapshot, block_reason),
        )

    @staticmethod
    def _rationale(
        snapshot: StrategySnapshot,
        block_reason: BlockReason,
        entry_reference: EntryReference = EntryReference.NONE,
        target_reference: TargetReference = TargetReference.NONE,
    ) -> tuple[str, ...]:
        ai = snapshot.ai_reasoning
        context = snapshot.market_context
        tokens = [
            f"bias_{context.market_bias.value}",
            f"confidence_{ai.confidence.value}",
            f"agreement_{ai.agreement_summary.value}",
            f"phase_{context.market_phase.value}",
        ]
        if entry_reference is not EntryReference.NONE:
            tokens.append(f"entry_{entry_reference.value}")
        if target_reference is not TargetReference.NONE:
            tokens.append(f"target_{target_reference.value}")
        if block_reason is not BlockReason.NONE:
            tokens.append(f"blocked_{block_reason.value}")
        return tuple(tokens)
