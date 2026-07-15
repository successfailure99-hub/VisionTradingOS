"""
Stateless Trade Journal V1 entry builder.
"""

from application.trade_lifecycle_v1.models import TradeLifecycleV1Snapshot
from engines.position_management_v1.enums import PositionExitReason
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
        market = strategy.market_context
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
            market_direction=market.direction,
            market_regime=market.regime,
            context_confidence=market.confidence,
            reasoning_direction=reasoning.direction,
            reasoning_conviction=reasoning.conviction,
            reasoning_confidence=reasoning.confidence,
            risk_decision=risk.decision,
            risk_approved_quantity=risk.approved_quantity,
            execution_side=intent.side,
            execution_fill_price=execution.average_fill_price or position.average_entry_price,
            execution_filled_quantity=execution.filled_quantity,
            lifecycle_snapshot=lifecycle,
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
