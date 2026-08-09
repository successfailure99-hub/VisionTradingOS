"""
Stateless Trade Journal V1 entry builder.
"""

from application.trade_lifecycle_v1.models import TradeLifecycleV1Snapshot
from core.enums.instrument import Instrument
from engines.option_paper_execution.enums import (
    OptionPaperPositionStatus,
    OptionPaperRiskDecision,
    OptionPaperUnderlyingDirection,
)
from engines.option_paper_execution.models import OptionPaperPositionSnapshot
from engines.position_management_v1.enums import PositionExitReason
from engines.risk_management_v2.enums import RiskDecision
from application.execution_runtime_v1.enums import ExecutionSide
from engines.strategy_decision_v2.enums import StrategyDecisionQuality, StrategyDirection, StrategySetupFamily
from engines.trade_journal_v1.configuration import TradeJournalV1Configuration
from engines.trade_journal_v1.enums import TradeCloseCategory, TradeOutcome
from engines.trade_journal_v1.models import TradeJournalEntry


class TradeJournalEntryBuilder:
    def __init__(self, configuration: TradeJournalV1Configuration | None = None):
        self._configuration = configuration or TradeJournalV1Configuration()

    def build(self, lifecycle: TradeLifecycleV1Snapshot) -> TradeJournalEntry:
        if not isinstance(lifecycle, TradeLifecycleV1Snapshot):
            raise TypeError("lifecycle must be TradeLifecycleV1Snapshot")
        if lifecycle.position_result is None or lifecycle.position_result.position is None:
            raise ValueError("lifecycle must contain a position result")
        position = lifecycle.position_result.position
        if self._configuration.require_closed_position:
            if position.closed_at is None or position.open_quantity != 0:
                raise ValueError("lifecycle must contain a closed position")
        if self._configuration.require_dry_run and position.dry_run is not True:
            raise ValueError("journal entry requires dry-run position")
        if self._configuration.require_analysis_only and position.analysis_only is not True:
            raise ValueError("journal entry requires analysis-only position")
        source = position.source
        execution = source.execution_result
        intent = source.execution_intent
        risk = source.risk_snapshot
        strategy = source.strategy_snapshot
        reasoning = strategy.ai_reasoning
        market_state = reasoning.market_state if reasoning is not None else None
        if position.closed_at is None:
            raise ValueError("closed position timestamp is required")
        if position.average_exit_price is None:
            raise ValueError("closed position exit price is required")
        risk_amount = risk.approved_risk_amount
        r_multiple = position.realized_pnl / risk_amount if risk_amount > 0 else None
        return TradeJournalEntry(
            trade_id=build_trade_id(position),
            instrument=position.instrument,
            opened_at=position.opened_at,
            closed_at=position.closed_at,
            duration_seconds=(position.closed_at - position.opened_at).total_seconds(),
            direction=strategy.direction,
            setup_family=strategy.setup_family,
            setup_quality=strategy.quality,
            entry_price=position.average_entry_price,
            average_exit_price=position.average_exit_price,
            initial_quantity=position.initial_quantity,
            closed_quantity=position.closed_quantity,
            invalidation_price=position.invalidation_price,
            objective_price=position.objective_price,
            realized_pnl=position.realized_pnl,
            risk_amount=risk_amount,
            r_multiple=r_multiple,
            outcome=_outcome(position.realized_pnl, self._configuration.flat_pnl_tolerance),
            exit_reason=position.exit_reason,
            close_category=_close_category(position.exit_reason),
            market_state=market_state.market_state.value if market_state is not None else "VISION_METHOD",
            market_phase=market_state.market_phase.value if market_state is not None else "VISION_METHOD",
            structural_confidence=market_state.confidence_level.value if market_state is not None else "VISION_METHOD",
            context_confidence=strategy.context_confidence,
            reasoning_direction=reasoning.direction.value if reasoning is not None else strategy.direction.value,
            reasoning_conviction=reasoning.conviction.value if reasoning is not None else strategy.quality.value,
            reasoning_confidence=reasoning.confidence if reasoning is not None else strategy.reasoning_confidence,
            risk_decision=risk.decision,
            risk_approved_quantity=risk.approved_quantity,
            execution_side=intent.side,
            execution_fill_price=execution.average_fill_price or position.average_entry_price,
            execution_filled_quantity=execution.filled_quantity,
            lifecycle_snapshot=lifecycle,
            trade_source=getattr(strategy, "trade_source", "STRATEGY_DECISION_V2"),
            trade_candidate_reference=getattr(strategy, "trade_candidate_reference", None),
            vision_method_snapshot_reference=getattr(strategy, "vision_method_snapshot_reference", None),
            vision_method_validation_reference=getattr(strategy, "vision_method_validation_reference", None),
        )

    def build_option_paper(self, position: OptionPaperPositionSnapshot) -> TradeJournalEntry:
        if not isinstance(position, OptionPaperPositionSnapshot):
            raise TypeError("position must be OptionPaperPositionSnapshot")
        candidate = position.candidate
        risk = position.risk
        closed = position.closed_at is not None and position.status is not OptionPaperPositionStatus.OPEN
        closed_at = position.closed_at or position.opened_at
        exit_premium = position.exit_premium if position.exit_premium is not None else position.current_premium
        realized = position.realized_pnl if closed else 0.0
        risk_amount = risk.planned_rupee_risk
        r_multiple = realized / risk_amount if risk_amount > 0 and closed else None
        return TradeJournalEntry(
            trade_id=position.position_id,
            instrument=Instrument(candidate.underlying.value),
            opened_at=position.opened_at,
            closed_at=closed_at,
            duration_seconds=(closed_at - position.opened_at).total_seconds(),
            direction=_option_direction(candidate.underlying_direction),
            setup_family=StrategySetupFamily.STRUCTURAL_RETEST,
            setup_quality=StrategyDecisionQuality.MODERATE,
            entry_price=position.entry_premium,
            average_exit_price=exit_premium,
            initial_quantity=position.quantity,
            closed_quantity=position.quantity,
            invalidation_price=risk.stop_premium,
            objective_price=risk.target_premium,
            realized_pnl=realized,
            risk_amount=risk_amount,
            r_multiple=r_multiple,
            outcome=_outcome(realized, self._configuration.flat_pnl_tolerance),
            exit_reason=_option_exit_reason(position),
            close_category=_close_category(_option_exit_reason(position)),
            market_state="VISION_METHOD",
            market_phase="VISION_METHOD",
            structural_confidence="VISION_METHOD",
            context_confidence=1.0,
            reasoning_direction=candidate.underlying_direction.value,
            reasoning_conviction=risk.decision.value,
            reasoning_confidence=1.0,
            risk_decision=_option_risk_decision(risk.decision),
            risk_approved_quantity=risk.approved_quantity,
            execution_side=ExecutionSide.SELL,
            execution_fill_price=position.entry_premium,
            execution_filled_quantity=position.quantity,
            lifecycle_snapshot=position,
            trade_source="VISION_METHOD_OPTION_SELLING_PAPER",
            trade_candidate_reference=candidate.source_trade_candidate_reference,
            vision_method_snapshot_reference=candidate.source_vision_reference,
            vision_method_validation_reference=candidate.source_trade_candidate_reference,
            record_state="closed" if closed else "open",
            instrument_type="OPTION",
            execution_style="DIRECTIONAL_OPTION_SELLING_PAPER",
            option_candidate_reference=candidate.candidate_id,
            option_position_reference=position.position_id,
            contract_trading_symbol=candidate.trading_symbol,
            instrument_token=candidate.instrument_token,
            expiry=candidate.expiry,
            strike=candidate.strike,
            option_type=candidate.option_type.value,
            transaction_type=candidate.transaction_type.value,
            moneyness=candidate.moneyness.value,
            itm_steps=candidate.itm_steps,
            lots=position.lots,
            lot_size=candidate.lot_size,
        )


def build_trade_id(position) -> str:
    return (
        f"{position.instrument.value}:"
        f"{position.position_id}:"
        f"{position.opened_at.isoformat()}:"
        f"{position.closed_at.isoformat()}"
    )


def _outcome(realized_pnl: float, tolerance: float) -> TradeOutcome:
    if realized_pnl > tolerance:
        return TradeOutcome.WIN
    if realized_pnl < -tolerance:
        return TradeOutcome.LOSS
    return TradeOutcome.FLAT


def _close_category(reason: PositionExitReason) -> TradeCloseCategory:
    if reason is PositionExitReason.OBJECTIVE:
        return TradeCloseCategory.OBJECTIVE
    if reason is PositionExitReason.INVALIDATION:
        return TradeCloseCategory.INVALIDATION
    if reason is PositionExitReason.MANUAL_DRY_RUN:
        return TradeCloseCategory.MANUAL_DRY_RUN
    return TradeCloseCategory.OTHER


def _option_direction(direction: OptionPaperUnderlyingDirection) -> StrategyDirection:
    if direction is OptionPaperUnderlyingDirection.BULLISH:
        return StrategyDirection.LONG
    return StrategyDirection.SHORT


def _option_risk_decision(decision: OptionPaperRiskDecision) -> RiskDecision:
    if decision is OptionPaperRiskDecision.APPROVED:
        return RiskDecision.APPROVED
    if decision is OptionPaperRiskDecision.APPROVED_REDUCED:
        return RiskDecision.APPROVED_REDUCED
    return RiskDecision.REJECTED


def _option_exit_reason(position: OptionPaperPositionSnapshot) -> PositionExitReason:
    if position.status is OptionPaperPositionStatus.TARGET_HIT:
        return PositionExitReason.OBJECTIVE
    if position.status in {OptionPaperPositionStatus.STOP_HIT, OptionPaperPositionStatus.INVALIDATED}:
        return PositionExitReason.INVALIDATION
    return PositionExitReason.MANUAL_DRY_RUN
