"""
Source validation for Position Management Engine V1.
"""

from application.execution_runtime_v1.enums import ExecutionDecision
from application.execution_runtime_v1.models import ExecutionResult
from engines.position_management_v1.configuration import PositionManagementV1Configuration


class PositionSourceValidator:
    def validate(
        self,
        result: ExecutionResult,
        configuration: PositionManagementV1Configuration,
    ) -> tuple[bool, tuple[str, ...]]:
        if not isinstance(result, ExecutionResult):
            raise TypeError("result must be ExecutionResult")
        messages = []
        if result.decision is not ExecutionDecision.ACCEPTED:
            messages.append("execution result must be accepted")
        if result.intent is None:
            messages.append("execution intent is required")
        if configuration.require_filled_execution and result.filled_quantity <= 0:
            messages.append("filled quantity must be positive")
        if result.average_fill_price is None:
            messages.append("average fill price is required")
        if result.intent is not None:
            if result.intent.dry_run is not True:
                messages.append("execution intent must be dry-run")
            if result.intent.analysis_only is not True:
                messages.append("execution intent must be analysis-only")
            if result.intent.risk_snapshot.approved_quantity < result.filled_quantity:
                messages.append("filled quantity cannot exceed risk-approved quantity")
        if messages:
            return False, tuple(messages)
        return True, ("execution result is valid for dry-run position creation",)
