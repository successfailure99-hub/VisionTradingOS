import pytest

from application.trade_lifecycle_v1 import TradeLifecycleStage
from tests.test_trade_lifecycle_v1_coordinator import coordinator
from tests.test_trade_lifecycle_v1_models import request


def test_manual_acknowledgement_fill_position_open_and_later_fill_rejected():
    item = coordinator()
    item.start()
    ack = item.process(request())
    assert ack.stage is TradeLifecycleStage.EXECUTION_ACKNOWLEDGED
    fill = item.confirm_execution_fill(fill_quantity=1, fill_price=108.0)
    assert fill.stage is TradeLifecycleStage.POSITION_OPEN
    assert fill.position_result.position.open_quantity == 1
    with pytest.raises(RuntimeError):
        item.confirm_execution_fill(fill_quantity=1, fill_price=108.0)
