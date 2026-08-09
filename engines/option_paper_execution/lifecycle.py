"""
Paper-only lifecycle helpers for directional short-option positions.
"""

from __future__ import annotations

from datetime import datetime

from .enums import OptionPaperPositionStatus, OptionPaperRiskDecision, OptionPaperUnderlyingDirection
from .models import OptionPaperPositionSnapshot, OptionPaperRiskSnapshot


def open_option_paper_position(risk: OptionPaperRiskSnapshot) -> OptionPaperPositionSnapshot:
    if risk.decision not in {OptionPaperRiskDecision.APPROVED, OptionPaperRiskDecision.APPROVED_REDUCED}:
        raise ValueError("approved option paper risk is required to open a paper position")
    return OptionPaperPositionSnapshot(
        position_id=":".join(("OSE1-PAPER", risk.candidate.candidate_id)),
        candidate=risk.candidate,
        risk=risk,
        status=OptionPaperPositionStatus.OPEN,
        opened_at=risk.timestamp,
        updated_at=risk.timestamp,
        closed_at=None,
        entry_premium=risk.entry_premium,
        current_premium=risk.entry_premium,
        exit_premium=None,
        quantity=risk.approved_quantity,
        lots=risk.approved_lots,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_pnl=0.0,
        exit_reason="open",
    )


def update_option_paper_position(
    position: OptionPaperPositionSnapshot,
    *,
    current_premium: float,
    underlying_price: float | None,
    timestamp: datetime,
) -> OptionPaperPositionSnapshot:
    if position.status is not OptionPaperPositionStatus.OPEN:
        return position
    pnl = round((position.entry_premium - current_premium) * position.quantity, 2)
    exit_status = None
    reason = "open"
    if current_premium <= position.risk.target_premium:
        exit_status = OptionPaperPositionStatus.TARGET_HIT
        reason = "premium target reached"
    elif current_premium >= position.risk.stop_premium:
        exit_status = OptionPaperPositionStatus.STOP_HIT
        reason = "premium stop reached"
    elif underlying_price is not None and _underlying_invalidated(position, underlying_price):
        exit_status = OptionPaperPositionStatus.INVALIDATED
        reason = "underlying structural invalidation reached"
    if exit_status is None:
        return OptionPaperPositionSnapshot(
            position_id=position.position_id,
            candidate=position.candidate,
            risk=position.risk,
            status=OptionPaperPositionStatus.OPEN,
            opened_at=position.opened_at,
            updated_at=timestamp,
            closed_at=None,
            entry_premium=position.entry_premium,
            current_premium=current_premium,
            exit_premium=None,
            quantity=position.quantity,
            lots=position.lots,
            unrealized_pnl=pnl,
            realized_pnl=0.0,
            total_pnl=pnl,
            exit_reason="open",
        )
    return OptionPaperPositionSnapshot(
        position_id=position.position_id,
        candidate=position.candidate,
        risk=position.risk,
        status=exit_status,
        opened_at=position.opened_at,
        updated_at=timestamp,
        closed_at=timestamp,
        entry_premium=position.entry_premium,
        current_premium=current_premium,
        exit_premium=current_premium,
        quantity=position.quantity,
        lots=position.lots,
        unrealized_pnl=0.0,
        realized_pnl=pnl,
        total_pnl=pnl,
        exit_reason=reason,
    )


def _underlying_invalidated(position: OptionPaperPositionSnapshot, underlying_price: float) -> bool:
    text = position.candidate.underlying_invalidation
    numbers = []
    for token in text.replace(",", " ").split():
        try:
            numbers.append(float(token))
        except ValueError:
            continue
    if not numbers:
        return False
    level = numbers[-1]
    if position.candidate.underlying_direction is OptionPaperUnderlyingDirection.BULLISH:
        return underlying_price <= level
    return underlying_price >= level
