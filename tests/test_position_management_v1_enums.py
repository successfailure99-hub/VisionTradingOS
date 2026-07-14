from engines.position_management_v1 import (
    PositionChange,
    PositionDecision,
    PositionExitReason,
    PositionPnlState,
    PositionSide,
    PositionStatus,
)


def test_exact_enum_values_and_exports():
    assert PositionSide.LONG.value == "long"
    assert PositionStatus.PARTIALLY_CLOSED.value == "partially_closed"
    assert PositionDecision.FULL_EXIT.value == "full_exit"
    assert PositionExitReason.MANUAL_DRY_RUN.value == "manual_dry_run"
    assert PositionChange.OBJECTIVE_REACHED.value == "objective_reached"
    assert PositionPnlState.PROFIT.value == "profit"
