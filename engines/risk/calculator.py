"""
Stateless Risk Engine V1 calculations.
"""

from math import floor

from engines.risk.enums import RiskDecision, RiskRejectionReason, RiskReductionReason, RiskTier
from engines.risk.models import RiskDecisionState, RiskSnapshot
from engines.strategy.enums import StrategyDecision, TradeDirection


class RiskCalculator:
    """
    Converts a strategy decision, explicit policy, account state, and
    numerical trade proposal into a pre-order risk approval decision.

    Risk Engine V1 does not fetch prices, place orders, estimate margin,
    include brokerage, taxes, slippage, Greeks, or persist account
    history. Monetary risk assumes one price point per unit equals one
    monetary unit. Calculations are O(1), deterministic, and event-free.
    """

    @staticmethod
    def calculate(snapshot: RiskSnapshot) -> RiskDecisionState:
        metrics = RiskCalculator._metrics(snapshot)
        reason = RiskCalculator._rejection_reason(snapshot, metrics)
        if reason is not RiskRejectionReason.NONE:
            return RiskCalculator._state(snapshot, metrics, RiskDecision.REJECTED, reason, 0, 0)

        approved_lots = snapshot.trade_plan.requested_lots
        approved_quantity = approved_lots * snapshot.trade_plan.lot_size
        estimated_risk = round(metrics["stop_distance"] * approved_quantity, 2)
        estimated_reward = round(metrics["target_distance"] * approved_quantity, 2)
        if estimated_risk > metrics["risk_budget"]:
            return RiskCalculator._state(
                snapshot,
                metrics,
                RiskDecision.REJECTED,
                RiskRejectionReason.INSUFFICIENT_RISK_BUDGET,
                0,
                0,
            )

        return RiskCalculator._state(
            snapshot,
            metrics,
            RiskDecision.APPROVED,
            RiskRejectionReason.NONE,
            approved_lots,
            approved_quantity,
            estimated_risk,
            estimated_reward,
        )

    @staticmethod
    def _metrics(snapshot: RiskSnapshot) -> dict[str, float | int | RiskReductionReason]:
        policy = snapshot.policy
        account = snapshot.account
        plan = snapshot.trade_plan

        stop_distance, target_distance = RiskCalculator._distances(snapshot)
        reward_risk_ratio = round(target_distance / stop_distance, 4) if stop_distance > 0 else 0.0

        daily_loss_limit = round(account.account_equity * policy.max_daily_loss_percent / 100, 2)
        realized_loss = max(-account.realized_pnl_today, 0)
        remaining_capacity = round(max(daily_loss_limit - realized_loss, 0), 2)

        reduction_reason = RiskCalculator._reduction_reason(snapshot)
        applied_percent = (
            policy.reduced_risk_percent
            if reduction_reason is not RiskReductionReason.NONE
            else policy.max_risk_percent
        )
        policy_budget = account.account_equity * applied_percent / 100
        risk_budget = round(min(policy_budget, remaining_capacity), 2)

        risk_per_lot = stop_distance * plan.lot_size
        lots_by_budget = floor(risk_budget / risk_per_lot) if risk_per_lot > 0 else 0
        maximum_lots = min(lots_by_budget, policy.max_lots)

        return {
            "stop_distance": round(stop_distance, 4),
            "target_distance": round(target_distance, 4),
            "reward_risk_ratio": reward_risk_ratio,
            "daily_loss_limit": daily_loss_limit,
            "remaining_capacity": remaining_capacity,
            "reduction_reason": reduction_reason,
            "applied_percent": applied_percent,
            "risk_budget": risk_budget,
            "maximum_lots": maximum_lots,
        }

    @staticmethod
    def _distances(snapshot: RiskSnapshot) -> tuple[float, float]:
        plan = snapshot.trade_plan
        direction = snapshot.strategy.direction
        if direction is TradeDirection.BULLISH and plan.stop_price < plan.entry_price < plan.target_price:
            return plan.entry_price - plan.stop_price, plan.target_price - plan.entry_price
        if direction is TradeDirection.BEARISH and plan.target_price < plan.entry_price < plan.stop_price:
            return plan.stop_price - plan.entry_price, plan.entry_price - plan.target_price
        return 0.0, 0.0

    @staticmethod
    def _reduction_reason(snapshot: RiskSnapshot) -> RiskReductionReason:
        policy = snapshot.policy
        account = snapshot.account
        loss_reduction = (
            policy.reduced_after_consecutive_losses > 0
            and account.consecutive_losses >= policy.reduced_after_consecutive_losses
            and account.consecutive_losses < policy.max_consecutive_losses
        )
        trade_reduction = (
            policy.reduced_after_trades > 0
            and account.trades_today >= policy.reduced_after_trades
            and account.trades_today < policy.max_trades_per_day
        )
        if loss_reduction and trade_reduction:
            return RiskReductionReason.BOTH
        if loss_reduction:
            return RiskReductionReason.RECENT_LOSSES
        if trade_reduction:
            return RiskReductionReason.DAILY_DRAWDOWN
        return RiskReductionReason.NONE

    @staticmethod
    def _rejection_reason(snapshot: RiskSnapshot, metrics: dict) -> RiskRejectionReason:
        strategy = snapshot.strategy
        policy = snapshot.policy
        account = snapshot.account
        plan = snapshot.trade_plan

        if strategy.decision is StrategyDecision.NO_TRADE:
            return RiskRejectionReason.STRATEGY_NO_TRADE
        if strategy.direction is TradeDirection.NONE:
            return RiskRejectionReason.INVALID_TRADE_DIRECTION
        if metrics["stop_distance"] <= 0 or metrics["target_distance"] <= 0:
            return RiskRejectionReason.INVALID_PRICE_STRUCTURE
        if max(-account.realized_pnl_today, 0) >= metrics["daily_loss_limit"]:
            return RiskRejectionReason.DAILY_LOSS_LIMIT_REACHED
        if account.consecutive_losses >= policy.max_consecutive_losses:
            return RiskRejectionReason.CONSECUTIVE_LOSS_LIMIT_REACHED
        if account.trades_today >= policy.max_trades_per_day:
            return RiskRejectionReason.DAILY_TRADE_LIMIT_REACHED
        if metrics["reward_risk_ratio"] < policy.minimum_reward_risk:
            return RiskRejectionReason.REWARD_RISK_BELOW_MINIMUM
        if metrics["risk_budget"] <= 0 or metrics["maximum_lots"] <= 0:
            return RiskRejectionReason.INSUFFICIENT_RISK_BUDGET
        if plan.requested_lots > metrics["maximum_lots"]:
            return RiskRejectionReason.REQUESTED_SIZE_EXCEEDS_LIMIT
        return RiskRejectionReason.NONE

    @staticmethod
    def _state(
        snapshot: RiskSnapshot,
        metrics: dict,
        decision: RiskDecision,
        rejection_reason: RiskRejectionReason,
        approved_lots: int,
        approved_quantity: int,
        estimated_risk: float = 0.0,
        estimated_reward: float = 0.0,
    ) -> RiskDecisionState:
        blocked = decision is RiskDecision.REJECTED
        risk_tier = RiskTier.BLOCKED if blocked else RiskCalculator._approved_tier(metrics["reduction_reason"])
        rationale = RiskCalculator._rationale(
            snapshot,
            risk_tier,
            decision,
            rejection_reason,
            metrics,
            approved_lots,
        )
        return RiskDecisionState(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            timestamp=snapshot.timestamp,
            decision=decision,
            risk_tier=risk_tier,
            rejection_reason=rejection_reason,
            reduction_reason=metrics["reduction_reason"] if not blocked else RiskReductionReason.NONE,
            direction=snapshot.strategy.direction,
            account_equity=round(snapshot.account.account_equity, 2),
            realized_pnl_today=round(snapshot.account.realized_pnl_today, 2),
            daily_loss_limit_amount=metrics["daily_loss_limit"],
            remaining_daily_loss_capacity=metrics["remaining_capacity"],
            applied_risk_percent=metrics["applied_percent"],
            risk_budget=metrics["risk_budget"],
            entry_price=snapshot.trade_plan.entry_price,
            stop_price=snapshot.trade_plan.stop_price,
            target_price=snapshot.trade_plan.target_price,
            stop_distance=metrics["stop_distance"],
            target_distance=metrics["target_distance"],
            reward_risk_ratio=metrics["reward_risk_ratio"],
            lot_size=snapshot.trade_plan.lot_size,
            requested_lots=snapshot.trade_plan.requested_lots,
            maximum_permitted_lots=metrics["maximum_lots"],
            approved_lots=approved_lots,
            approved_quantity=approved_quantity,
            estimated_risk_amount=estimated_risk if not blocked else 0.0,
            estimated_reward_amount=estimated_reward if not blocked else 0.0,
            rationale=rationale,
        )

    @staticmethod
    def _approved_tier(reduction_reason: RiskReductionReason) -> RiskTier:
        if reduction_reason is RiskReductionReason.NONE:
            return RiskTier.STANDARD
        return RiskTier.REDUCED

    @staticmethod
    def _rationale(
        snapshot: RiskSnapshot,
        risk_tier: RiskTier,
        decision: RiskDecision,
        rejection_reason: RiskRejectionReason,
        metrics: dict,
        approved_lots: int,
    ) -> tuple[str, ...]:
        tokens = [
            "strategy_trade_eligible"
            if snapshot.strategy.decision is StrategyDecision.TRADE_ELIGIBLE
            else "strategy_no_trade",
            f"direction_{snapshot.strategy.direction.value}",
            f"risk_tier_{risk_tier.value}",
        ]
        if decision is RiskDecision.APPROVED:
            reduction_reason = metrics["reduction_reason"]
            if reduction_reason is not RiskReductionReason.NONE:
                tokens.append(f"reduced_{reduction_reason.value}")
            tokens.extend(
                (
                    f"risk_percent_{metrics['applied_percent']}",
                    f"reward_risk_{metrics['reward_risk_ratio']}",
                    f"requested_lots_{snapshot.trade_plan.requested_lots}",
                    f"approved_lots_{approved_lots}",
                )
            )
        else:
            tokens.append(f"rejected_{rejection_reason.value}")
        return tuple(tokens)
