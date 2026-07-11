"""
Stateless Trade Journal Engine V1 calculator.
"""

from engines.risk.enums import RiskDecision
from engines.strategy.enums import StrategyDecision
from engines.trade_journal.enums import TradeCompliance, TradeOutcome
from engines.trade_journal.models import TradeJournalRecord, TradeJournalSnapshot, TradeJournalSummary


class TradeJournalCalculator:
    """
    Deterministic in-memory journal calculations.

    V1 creates immutable records for completed position lifecycles only.
    It does not persist data, calculate fees or net P&L, access files,
    databases, networks, brokers, pandas, or NumPy. R-multiple uses planned
    risk, and realized_gross_pnl excludes brokerage, taxes, slippage, and
    charges.
    """

    @staticmethod
    def create_record(
        snapshot: TradeJournalSnapshot,
    ) -> TradeJournalRecord:
        outcome = TradeJournalCalculator._outcome(snapshot.realized_gross_pnl)
        compliance = TradeJournalCalculator._compliance(snapshot)
        holding_seconds = int((snapshot.closed_at - snapshot.opened_at).total_seconds())
        return TradeJournalRecord(
            trade_id=snapshot.trade_id,
            symbol=snapshot.symbol,
            exchange=snapshot.exchange,
            timeframe=snapshot.timeframe,
            opened_at=snapshot.opened_at,
            closed_at=snapshot.closed_at,
            holding_seconds=holding_seconds,
            direction=snapshot.direction,
            outcome=outcome,
            compliance=compliance,
            exit_type=snapshot.exit_type,
            entry_quantity=snapshot.entry_quantity,
            exit_quantity=snapshot.exit_quantity,
            average_entry_price=snapshot.average_entry_price,
            average_exit_price=snapshot.average_exit_price,
            planned_stop_price=snapshot.planned_stop_price,
            planned_target_price=snapshot.planned_target_price,
            planned_risk_amount=snapshot.planned_risk_amount,
            planned_reward_amount=snapshot.planned_reward_amount,
            realized_gross_pnl=round(snapshot.realized_gross_pnl, 2),
            r_multiple=round(snapshot.realized_gross_pnl / snapshot.planned_risk_amount, 4),
            reward_risk_planned=round(snapshot.planned_reward_amount / snapshot.planned_risk_amount, 4),
            strategy_decision=snapshot.strategy.decision,
            setup_quality=snapshot.strategy.setup_quality,
            market_bias=snapshot.strategy.market_bias,
            market_phase=snapshot.strategy.market_phase,
            reasoning_confidence=snapshot.ai_reasoning.confidence,
            trading_suitability=snapshot.ai_reasoning.trading_suitability,
            strategy_rationale=tuple(snapshot.strategy.rationale),
            ai_explanation=(snapshot.ai_reasoning.explanation,),
            missing_information=tuple(snapshot.ai_reasoning.missing_information),
            entry_order_ids=snapshot.entry_order_ids,
            exit_order_ids=snapshot.exit_order_ids,
        )

    @staticmethod
    def calculate_summary(
        records: tuple[TradeJournalRecord, ...],
    ) -> TradeJournalSummary:
        if not records:
            return TradeJournalCalculator.empty_summary()

        total = len(records)
        wins = tuple(record for record in records if record.outcome is TradeOutcome.WIN)
        losses = tuple(record for record in records if record.outcome is TradeOutcome.LOSS)
        breakeven = tuple(record for record in records if record.outcome is TradeOutcome.BREAKEVEN)
        compliant = tuple(record for record in records if record.compliance is TradeCompliance.COMPLIANT)
        gross_profit = round(sum(record.realized_gross_pnl for record in wins), 2)
        gross_loss = round(abs(sum(record.realized_gross_pnl for record in losses)), 2)
        total_pnl = round(sum(record.realized_gross_pnl for record in records), 2)
        average_trade = round(total_pnl / total, 2)
        r_values = tuple(record.r_multiple for record in records if record.r_multiple is not None)
        return TradeJournalSummary(
            total_trades=total,
            winning_trades=len(wins),
            losing_trades=len(losses),
            breakeven_trades=len(breakeven),
            compliant_trades=len(compliant),
            non_compliant_trades=total - len(compliant),
            total_gross_pnl=total_pnl,
            average_trade_pnl=average_trade,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            win_rate=round((len(wins) / total) * 100, 2),
            loss_rate=round((len(losses) / total) * 100, 2),
            average_win=round(gross_profit / len(wins), 2) if wins else None,
            average_loss=round(sum(record.realized_gross_pnl for record in losses) / len(losses), 2) if losses else None,
            profit_factor=round(gross_profit / gross_loss, 4) if gross_loss > 0 else None,
            expectancy=average_trade,
            average_r_multiple=round(sum(r_values) / len(r_values), 4) if r_values else None,
            best_trade_pnl=max(record.realized_gross_pnl for record in records),
            worst_trade_pnl=min(record.realized_gross_pnl for record in records),
            average_holding_seconds=round(sum(record.holding_seconds for record in records) / total, 2),
        )

    @staticmethod
    def empty_summary() -> TradeJournalSummary:
        return TradeJournalSummary(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            breakeven_trades=0,
            compliant_trades=0,
            non_compliant_trades=0,
            total_gross_pnl=0.0,
            average_trade_pnl=0.0,
            gross_profit=0.0,
            gross_loss=0.0,
            win_rate=None,
            loss_rate=None,
            average_win=None,
            average_loss=None,
            profit_factor=None,
            expectancy=None,
            average_r_multiple=None,
            best_trade_pnl=None,
            worst_trade_pnl=None,
            average_holding_seconds=None,
        )

    @staticmethod
    def _outcome(realized_gross_pnl: float) -> TradeOutcome:
        if realized_gross_pnl > 0:
            return TradeOutcome.WIN
        if realized_gross_pnl < 0:
            return TradeOutcome.LOSS
        return TradeOutcome.BREAKEVEN

    @staticmethod
    def _compliance(snapshot: TradeJournalSnapshot) -> TradeCompliance:
        if (
            snapshot.entry_quantity == snapshot.risk.approved_quantity
            and snapshot.average_entry_price == snapshot.risk.entry_price
            and snapshot.planned_stop_price == snapshot.risk.stop_price
            and snapshot.planned_target_price == snapshot.risk.target_price
            and snapshot.planned_risk_amount == snapshot.risk.estimated_risk_amount
            and snapshot.strategy.decision is StrategyDecision.TRADE_ELIGIBLE
            and snapshot.risk.decision is RiskDecision.APPROVED
        ):
            return TradeCompliance.COMPLIANT
        return TradeCompliance.NON_COMPLIANT
