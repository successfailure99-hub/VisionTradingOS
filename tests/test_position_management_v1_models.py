from dataclasses import FrozenInstanceError, replace

import pytest

from application.execution_runtime_v1 import ExecutionFillPolicy, ExecutionRuntimeV1, ExecutionRuntimeV1Configuration
from core.enums.instrument import Instrument
from engines.position_management_v1 import (
    ManagedPosition,
    PositionManagementCalculator,
    PositionManagementResult,
    PositionManagementV1Configuration,
    PositionManagementV1Snapshot,
    PositionPriceUpdate,
    PositionSource,
    PositionDecision,
    PositionChange,
    PositionStatus,
    build_position_id,
)
from tests.test_risk_management_v2_calculator import calculate, risk_input, strategy


def filled_execution(kind="bullish"):
    risk = calculate(
        risk_input(
            strategy(kind),
            proposed_entry_price=93.0 if kind == "bearish" else 108.0,
            proposed_invalidation_price=143.0 if kind == "bearish" else 83.0,
            proposed_objective_price=13.0 if kind == "bearish" else 148.0,
        )
    )
    runtime = ExecutionRuntimeV1(
        instrument=Instrument.NIFTY,
        configuration=ExecutionRuntimeV1Configuration(fill_policy=ExecutionFillPolicy.IMMEDIATE_FULL, require_manual_fill_confirmation=True),
    )
    runtime.start()
    return runtime.submit(risk)


def position(kind="bullish"):
    result = filled_execution(kind)
    return PositionManagementCalculator().open_from_execution(result, PositionManagementV1Configuration(), timestamp=result.lifecycle[-1].timestamp)


def test_models_are_frozen_slotted_consistent_and_deterministic():
    pos = position()
    source = pos.source

    assert isinstance(source, PositionSource)
    assert pos.position_id == build_position_id(source)
    assert pos.status is PositionStatus.OPEN
    assert pos.open_quantity == pos.initial_quantity
    assert pos.total_pnl == pos.realized_pnl + pos.unrealized_pnl
    assert pos.dry_run is True
    assert pos.analysis_only is True
    assert not any("broker" in field or "order_id" in field or "account_id" in field for field in ManagedPosition.__dataclass_fields__)
    with pytest.raises(FrozenInstanceError):
        pos.open_quantity = 0


def test_price_geometry_timestamp_and_snapshot_rules():
    pos = position()
    update = PositionPriceUpdate(pos.instrument, pos.updated_at, pos.average_entry_price + 1)
    result = PositionManagementResult(PositionDecision.HOLD, pos, PositionChange.OPENED, "Opened.")
    snapshot = PositionManagementV1Snapshot(pos.instrument, pos.updated_at, pos, result, 1, 0, 0, 0, 0, 0.0, 0.0, True, 1, None)

    assert update.market_price > pos.average_entry_price
    assert snapshot.has_open_position is True
    with pytest.raises(ValueError):
        replace(pos, open_quantity=0)
    with pytest.raises(ValueError):
        PositionManagementV1Snapshot(pos.instrument, pos.updated_at, None, result, 0, 0, 0, 0, 0, 0.0, 0.0, True, 0, None)
