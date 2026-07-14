from datetime import timedelta

from application.bootstrap import ApplicationBootstrap
from application.enums import ExecutionSafetyMode
from application.trade_lifecycle_v1 import TradeLifecycleStage
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.position_management_v1 import PositionPriceUpdate
from tests.test_trade_lifecycle_v1_coordinator import coordinator
from tests.test_trade_lifecycle_v1_gating import test_risk_rejection_stops_before_execution
from tests.test_trade_lifecycle_v1_models import request


def test_no_network_end_to_end_lifecycle_and_application_defaults():
    item = coordinator()
    item.start()
    acknowledged = item.process(request())
    opened = item.confirm_execution_fill(fill_quantity=2, fill_price=108.0)
    pos = opened.position_result.position
    profitable = item.update_position_price(PositionPriceUpdate(Instrument.NIFTY, pos.updated_at + timedelta(minutes=1), 118.0))
    partial = item.partial_exit_position(quantity=1, exit_price=118.0)
    closed = item.close_position(exit_price=119.0)

    assert acknowledged.stage is TradeLifecycleStage.EXECUTION_ACKNOWLEDGED
    assert opened.stage is TradeLifecycleStage.POSITION_OPEN
    assert profitable.position_result.position.unrealized_pnl > 0
    assert partial.stage is TradeLifecycleStage.POSITION_PARTIALLY_CLOSED
    assert closed.stage is TradeLifecycleStage.POSITION_CLOSED
    assert isinstance(item.history(), tuple)
    lifecycle = ApplicationBootstrap().create_application()
    app_snapshot = lifecycle.snapshot().orchestrator_snapshot
    assert app_snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert app_snapshot.broker_mode is BrokerExecutionMode.DRY_RUN


def test_integration_risk_rejection_smoke():
    test_risk_rejection_stops_before_execution()
