"""
Paper-only short-option risk evaluation for OSE-1.
"""

from __future__ import annotations

from .enums import OptionPaperRiskDecision
from .models import DirectionalOptionSellingConfiguration, OptionPaperRiskSnapshot, OptionTradeCandidate


def evaluate_option_paper_risk(
    candidate: OptionTradeCandidate,
    configuration: DirectionalOptionSellingConfiguration,
    *,
    open_position_exists: bool = False,
    margin_available: float | None = None,
) -> OptionPaperRiskSnapshot:
    requested_lots = configuration.maximum_lots_for(candidate.underlying)
    entry = candidate.bid if candidate.bid is not None and candidate.bid > 0 else candidate.premium_reference
    stop = round(entry * configuration.stop_premium_multiplier, 2)
    target = round(entry * configuration.target_premium_multiplier, 2)
    risk_per_unit = round(stop - entry, 2)
    reward_per_unit = round(entry - target, 2)
    per_lot_risk = risk_per_unit * candidate.lot_size
    risk_budget = configuration.paper_capital * configuration.risk_fraction_per_trade
    warnings: tuple[str, ...] = ()
    if open_position_exists:
        return _snapshot(
            candidate,
            configuration,
            OptionPaperRiskDecision.REJECTED,
            requested_lots,
            0,
            entry,
            stop,
            target,
            risk_per_unit,
            reward_per_unit,
            margin_available,
            "Existing directional option paper position is already open.",
            warnings,
        )
    if per_lot_risk <= 0:
        approved_lots = 0
    else:
        approved_lots = min(requested_lots, int(risk_budget // per_lot_risk))
    if approved_lots <= 0:
        decision = OptionPaperRiskDecision.REJECTED
        reason = "Planned premium risk exceeds configured paper risk budget."
    elif approved_lots < requested_lots:
        decision = OptionPaperRiskDecision.APPROVED_REDUCED
        reason = f"Reduced from {requested_lots} lots to {approved_lots} lots by paper risk budget."
    else:
        decision = OptionPaperRiskDecision.APPROVED
        reason = f"Approved {approved_lots} lots for paper-only directional option selling."
    return _snapshot(
        candidate,
        configuration,
        decision,
        requested_lots,
        approved_lots,
        entry,
        stop,
        target,
        risk_per_unit,
        reward_per_unit,
        margin_available,
        reason,
        warnings,
    )


def _snapshot(
    candidate: OptionTradeCandidate,
    configuration: DirectionalOptionSellingConfiguration,
    decision: OptionPaperRiskDecision,
    requested_lots: int,
    approved_lots: int,
    entry: float,
    stop: float,
    target: float,
    risk_per_unit: float,
    reward_per_unit: float,
    margin_available: float | None,
    reason: str,
    warnings: tuple[str, ...],
) -> OptionPaperRiskSnapshot:
    quantity = approved_lots * candidate.lot_size
    return OptionPaperRiskSnapshot(
        candidate=candidate,
        timestamp=candidate.created_at,
        decision=decision,
        requested_lots=requested_lots,
        approved_lots=approved_lots,
        approved_quantity=quantity,
        entry_premium=entry,
        stop_premium=stop,
        target_premium=target,
        risk_per_unit=risk_per_unit,
        reward_per_unit=reward_per_unit,
        planned_rupee_risk=round(risk_per_unit * quantity, 2),
        planned_rupee_reward=round(reward_per_unit * quantity, 2),
        paper_capital=configuration.paper_capital,
        margin_available=margin_available,
        reason=reason,
        warnings=warnings,
    )
