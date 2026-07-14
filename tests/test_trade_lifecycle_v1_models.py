from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from application.execution_runtime_v1 import ExecutionRuntimeV1
from application.trade_lifecycle_v1 import (
    TradeLifecycleBlockSource,
    TradeLifecycleOutcome,
    TradeLifecycleStage,
    TradeLifecycleStageRecord,
    TradeLifecycleStatus,
    TradeLifecycleV1Request,
    TradeLifecycleV1Snapshot,
)
from core.enums.instrument import Instrument
from engines.market_context_v2 import MarketContextV2Engine
from engines.position_management_v1 import PositionManagementV1Engine
from engines.risk_management_v2 import AccountRiskState, InstrumentExposureState, SessionRiskState
from tests.test_market_context_v2_integration import NOW, input_bundle
from tests.test_strategy_decision_v2_integration import cam, cpr, vwap
from engines.option_chain_analytics.enums import OptionAnalyticsBias
from engines.price_action.enums import Trend


def request():
    context = MarketContextV2Engine(instrument=Instrument.NIFTY).process(input_bundle(Trend.BULLISH, OptionAnalyticsBias.BULLISH, 108.0))
    return TradeLifecycleV1Request(
        market_context=context,
        current_price=108.0,
        account_risk_state=AccountRiskState(NOW, 10000.0, 10000.0, 10000.0, 10000.0, 0.0, 0.0, 0.0),
        session_risk_state=SessionRiskState(date(2026, 7, 14), 0, 0, 0, 0, 0.0),
        instrument_exposure_state=InstrumentExposureState(Instrument.NIFTY, 0, 0.0, 0.0),
        proposed_entry_price=108.0,
        proposed_invalidation_price=83.0,
        proposed_objective_price=148.0,
        camarilla=cam(),
        cpr=cpr(),
        vwap=vwap(),
    )


def test_request_stage_record_and_snapshot_validation():
    req = request()
    record = TradeLifecycleStageRecord(1, NOW, TradeLifecycleStage.CONTEXT_RECEIVED, TradeLifecycleOutcome.IN_PROGRESS, "Context received.")
    execution_snapshot = ExecutionRuntimeV1(instrument=Instrument.NIFTY).snapshot()
    position_snapshot = PositionManagementV1Engine(instrument=Instrument.NIFTY).snapshot()
    snapshot = TradeLifecycleV1Snapshot(
        Instrument.NIFTY,
        NOW,
        TradeLifecycleStatus.CREATED,
        TradeLifecycleStage.IDLE,
        TradeLifecycleOutcome.IN_PROGRESS,
        __import__("application.trade_lifecycle_v1", fromlist=["TradeLifecycleChange"]).TradeLifecycleChange.INITIAL,
        TradeLifecycleBlockSource.NONE,
        req.market_context,
        None,
        None,
        None,
        None,
        None,
        execution_snapshot,
        position_snapshot,
        (record,),
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        False,
        False,
        None,
        None,
        None,
        None,
    )

    assert req.market_context.instrument is Instrument.NIFTY
    assert snapshot.stage_records == (record,)
    with pytest.raises(FrozenInstanceError):
        snapshot.processing_count = 2
    with pytest.raises(ValueError):
        TradeLifecycleStageRecord(0, NOW, TradeLifecycleStage.IDLE, TradeLifecycleOutcome.IN_PROGRESS, "Bad.")
    assert not any("owner" in field or "credential" in field or "raw_tick" in field for field in req.__dataclass_fields__)
