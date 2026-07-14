"""
Deterministic dry-run execution simulator.
"""

from dataclasses import replace
from datetime import datetime
from math import isfinite
from numbers import Real

from application.execution_runtime_v1.configuration import ExecutionRuntimeV1Configuration
from application.execution_runtime_v1.enums import (
    ExecutionDecision,
    ExecutionFillPolicy,
    ExecutionIntentStatus,
)
from application.execution_runtime_v1.models import (
    ExecutionIntent,
    ExecutionLifecycleEvent,
    ExecutionResult,
)


class DryRunExecutionSimulator:
    def submit(
        self,
        intent: ExecutionIntent,
        configuration: ExecutionRuntimeV1Configuration,
        *,
        timestamp: datetime,
    ) -> ExecutionResult:
        _aware(timestamp, "timestamp")
        lifecycle = [
            _event(1, timestamp, ExecutionIntentStatus.CREATED, "Execution intent created.", 0, intent.quantity, None),
            _event(2, timestamp, ExecutionIntentStatus.VALIDATED, "Execution intent validated for dry-run.", 0, intent.quantity, None),
            _event(3, timestamp, ExecutionIntentStatus.SUBMITTED_DRY_RUN, "Execution intent submitted to dry-run simulator.", 0, intent.quantity, None),
            _event(4, timestamp, ExecutionIntentStatus.ACKNOWLEDGED, "Dry-run simulator acknowledged the intent.", 0, intent.quantity, None),
        ]
        filled = 0
        average = None
        status = ExecutionIntentStatus.ACKNOWLEDGED
        if configuration.fill_policy is ExecutionFillPolicy.IMMEDIATE_FULL:
            filled = intent.quantity
            average = intent.reference_entry_price
            status = ExecutionIntentStatus.FILLED
            lifecycle.append(_event(5, timestamp, status, "Dry-run simulator filled the full quantity.", filled, 0, average))
        elif configuration.fill_policy is ExecutionFillPolicy.IMMEDIATE_PARTIAL:
            filled = max(1, intent.quantity // 2)
            if filled >= intent.quantity:
                filled = intent.quantity
                status = ExecutionIntentStatus.FILLED
            else:
                status = ExecutionIntentStatus.PARTIALLY_FILLED
            average = intent.reference_entry_price
            lifecycle.append(_event(5, timestamp, status, "Dry-run simulator filled a partial quantity.", filled, intent.quantity - filled, average))
        updated_intent = replace(intent, status=status)
        return ExecutionResult(
            decision=ExecutionDecision.ACCEPTED,
            intent=updated_intent,
            lifecycle=tuple(lifecycle),
            accepted_quantity=intent.quantity,
            filled_quantity=filled,
            remaining_quantity=intent.quantity - filled,
            average_fill_price=average,
            message="Dry-run execution accepted.",
        )

    def confirm_fill(
        self,
        intent: ExecutionIntent,
        *,
        fill_quantity: int,
        fill_price: float,
        timestamp: datetime,
        prior_result: ExecutionResult,
    ) -> ExecutionResult:
        _aware(timestamp, "timestamp")
        _positive_int(fill_quantity, "fill_quantity")
        fill_price = _positive_real(fill_price, "fill_price")
        if prior_result.remaining_quantity <= 0:
            raise ValueError("cannot fill an already completed execution")
        if fill_quantity > prior_result.remaining_quantity:
            raise ValueError("fill quantity cannot exceed remaining quantity")
        if intent.status not in {ExecutionIntentStatus.ACKNOWLEDGED, ExecutionIntentStatus.PARTIALLY_FILLED}:
            raise ValueError("fill confirmation requires acknowledged or partially filled intent")
        filled = prior_result.filled_quantity + fill_quantity
        remaining = prior_result.accepted_quantity - filled
        status = ExecutionIntentStatus.FILLED if remaining == 0 else ExecutionIntentStatus.PARTIALLY_FILLED
        notional = (prior_result.average_fill_price or 0.0) * prior_result.filled_quantity
        average = (notional + fill_price * fill_quantity) / filled
        event = _event(
            len(prior_result.lifecycle) + 1,
            timestamp,
            status,
            "Dry-run fill confirmation recorded.",
            filled,
            remaining,
            fill_price,
        )
        return ExecutionResult(
            decision=ExecutionDecision.ACCEPTED,
            intent=replace(intent, status=status),
            lifecycle=prior_result.lifecycle + (event,),
            accepted_quantity=prior_result.accepted_quantity,
            filled_quantity=filled,
            remaining_quantity=remaining,
            average_fill_price=average,
            message="Dry-run fill confirmation accepted.",
        )

    def cancel(
        self,
        intent: ExecutionIntent,
        *,
        timestamp: datetime,
        prior_result: ExecutionResult,
    ) -> ExecutionResult:
        _aware(timestamp, "timestamp")
        if prior_result.remaining_quantity <= 0:
            raise ValueError("cannot cancel a fully filled execution")
        event = _event(
            len(prior_result.lifecycle) + 1,
            timestamp,
            ExecutionIntentStatus.CANCELLED,
            "Dry-run execution cancelled.",
            prior_result.filled_quantity,
            prior_result.remaining_quantity,
            None,
        )
        return ExecutionResult(
            decision=ExecutionDecision.ACCEPTED,
            intent=replace(intent, status=ExecutionIntentStatus.CANCELLED),
            lifecycle=prior_result.lifecycle + (event,),
            accepted_quantity=prior_result.accepted_quantity,
            filled_quantity=prior_result.filled_quantity,
            remaining_quantity=prior_result.remaining_quantity,
            average_fill_price=prior_result.average_fill_price,
            message="Dry-run execution cancelled.",
        )


def _event(sequence, timestamp, status, message, filled, remaining, price):
    return ExecutionLifecycleEvent(sequence, timestamp, status, message, filled, remaining, price)


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _positive_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be positive")
    return number


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive integer")
