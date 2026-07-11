"""
Tests for Zerodha Broker Adapter V1.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta

from brokers import BrokerOrderClient
from brokers.zerodha import (
    BrokerAction,
    BrokerExecutionMode,
    BrokerExecutionResult,
    BrokerRequest,
    BrokerResultStatus,
    ZerodhaBrokerAdapter,
    ZerodhaOrderMapper,
    ZerodhaOrderStatus,
    ZerodhaOrderUpdate,
    ZerodhaResponseParser,
)
from core.event_bus import EventBus
from engines.order_management.enums import (
    OrderCommandType,
    OrderRejectionReason,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
)
from engines.order_management.models import OrderCommand, OrderState
from engines.order_management.order_management_engine import OrderManagementEngine


TS = datetime(2026, 7, 10, 10, 0)


def assert_raises(expected_error, callback):
    try:
        callback()
    except expected_error:
        return
    raise AssertionError(f"Expected {expected_error}")


def order(**overrides):
    values = {
        "client_order_id": "order-1",
        "broker_order_id": None,
        "symbol": "NIFTY",
        "exchange": "NSE",
        "timeframe": "1m",
        "created_at": TS,
        "updated_at": TS,
        "side": OrderSide.BUY,
        "order_type": OrderType.MARKET,
        "product_type": ProductType.INTRADAY,
        "status": OrderStatus.PENDING_SUBMISSION,
        "quantity": 150,
        "filled_quantity": 0,
        "remaining_quantity": 150,
        "average_fill_price": None,
        "limit_price": None,
        "trigger_price": None,
        "risk_entry_price": 100.0,
        "risk_stop_price": 90.0,
        "risk_target_price": 120.0,
        "estimated_risk_amount": 1500.0,
        "rejection_reason": OrderRejectionReason.NONE,
        "rejection_message": None,
        "version": 1,
    }
    values.update(overrides)
    return OrderState(**values)


def submitted(**overrides):
    values = {
        "broker_order_id": "BRK-1",
        "status": OrderStatus.SUBMITTED,
        "updated_at": TS + timedelta(minutes=1),
        "version": 2,
    }
    values.update(overrides)
    return order(**values)


def modify_command(**overrides):
    values = {
        "command_type": OrderCommandType.MODIFY,
        "client_order_id": "order-1",
        "timestamp": TS + timedelta(minutes=2),
        "new_quantity": 120,
    }
    values.update(overrides)
    return OrderCommand(**values)


def update(**overrides):
    values = {
        "order_id": "BRK-1",
        "status": ZerodhaOrderStatus.OPEN,
        "timestamp": TS + timedelta(minutes=1),
        "filled_quantity": 0,
        "pending_quantity": 150,
        "average_price": 0.0,
        "status_message": None,
    }
    values.update(overrides)
    return ZerodhaOrderUpdate(**values)


class FakeClient:
    def __init__(self, result="BRK-1", raise_error=False):
        self.result = result
        self.raise_error = raise_error
        self.calls = []

    def place_order(self, **kwargs):
        self.calls.append(("place", kwargs))
        if self.raise_error:
            raise RuntimeError("broker down")
        return self.result

    def modify_order(self, **kwargs):
        self.calls.append(("modify", kwargs))
        if self.raise_error:
            raise RuntimeError("broker down")
        return self.result

    def cancel_order(self, **kwargs):
        self.calls.append(("cancel", kwargs))
        if self.raise_error:
            raise RuntimeError("broker down")
        return self.result


def test_protocol_exports_models_slots_and_default_mode():
    from brokers import __all__ as broker_exports
    from brokers.zerodha import __all__ as zerodha_exports

    assert broker_exports == ["BrokerOrderClient"]
    assert "ZerodhaBrokerAdapter" in zerodha_exports
    assert "ZerodhaResponseParser" in zerodha_exports
    assert BrokerExecutionMode.DRY_RUN.value == "dry_run"
    assert BrokerAction.PLACE.value == "place"
    assert BrokerResultStatus.ACCEPTED.value == "accepted"
    assert ZerodhaOrderStatus.COMPLETE.value == "COMPLETE"
    assert BrokerOrderClient is not None

    request = ZerodhaOrderMapper.place_request(order())
    result = ZerodhaBrokerAdapter().place(order())
    parsed = update()
    assert isinstance(request, BrokerRequest)
    assert isinstance(result, BrokerExecutionResult)
    assert isinstance(parsed, ZerodhaOrderUpdate)
    assert request.as_dict()["variety"] == "regular"
    assert not hasattr(request, "__dict__")
    assert not hasattr(result, "__dict__")
    assert not hasattr(parsed, "__dict__")
    assert_raises(FrozenInstanceError, lambda: setattr(request, "client_order_id", "x"))
    assert ZerodhaBrokerAdapter().mode is BrokerExecutionMode.DRY_RUN
    assert_raises(ValueError, lambda: ZerodhaBrokerAdapter(mode=BrokerExecutionMode.CLIENT))


def test_place_mapping_side_type_product_validity_variety_and_tag_rules():
    buy_market = ZerodhaOrderMapper.place_request(order())
    payload = buy_market.as_dict()
    assert payload == {
        "variety": "regular",
        "tradingsymbol": "NIFTY",
        "exchange": "NSE",
        "transaction_type": "BUY",
        "order_type": "MARKET",
        "quantity": 150,
        "product": "MIS",
        "validity": "DAY",
        "tag": "order1",
    }

    sell_limit = ZerodhaOrderMapper.place_request(
        order(client_order_id="sell-order-123456789000", side=OrderSide.SELL, order_type=OrderType.LIMIT, limit_price=100.0)
    ).as_dict()
    assert sell_limit["transaction_type"] == "SELL"
    assert sell_limit["order_type"] == "LIMIT"
    assert sell_limit["price"] == 100.0
    assert sell_limit["tag"] == "sellorder12345678900"

    stop_market = ZerodhaOrderMapper.place_request(
        order(client_order_id="stop1", order_type=OrderType.STOP_MARKET, trigger_price=100.0)
    ).as_dict()
    assert stop_market["order_type"] == "SL-M"
    assert stop_market["trigger_price"] == 100.0
    assert "price" not in stop_market

    stop_limit = ZerodhaOrderMapper.place_request(
        order(client_order_id="stop2", order_type=OrderType.STOP_LIMIT, limit_price=101.0, trigger_price=100.0)
    ).as_dict()
    assert stop_limit["order_type"] == "SL"
    assert stop_limit["price"] == 101.0
    assert stop_limit["trigger_price"] == 100.0

    assert_raises(ValueError, lambda: ZerodhaOrderMapper.normalize_tag("---"))
    assert_raises(ValueError, lambda: ZerodhaOrderMapper.place_request(order(status=OrderStatus.SUBMITTED)))
    assert_raises(ValueError, lambda: ZerodhaOrderMapper.place_request(order(broker_order_id="BRK-1")))


def test_modify_and_cancel_mapping_validation():
    limit_order = submitted(order_type=OrderType.LIMIT, limit_price=100.0)
    modify = ZerodhaOrderMapper.modify_request(limit_order, modify_command(new_quantity=120, new_limit_price=100.0))
    assert modify.action is BrokerAction.MODIFY
    assert modify.broker_order_id == "BRK-1"
    assert modify.as_dict() == {
        "variety": "regular",
        "order_id": "BRK-1",
        "order_type": "LIMIT",
        "quantity": 120,
        "validity": "DAY",
        "price": 100.0,
    }

    stop = submitted(order_type=OrderType.STOP_LIMIT, limit_price=101.0, trigger_price=100.0)
    stop_modify = ZerodhaOrderMapper.modify_request(
        stop,
        modify_command(new_quantity=140, new_limit_price=101.0, new_trigger_price=100.0),
    ).as_dict()
    assert stop_modify["price"] == 101.0
    assert stop_modify["trigger_price"] == 100.0

    cancel = ZerodhaOrderMapper.cancel_request(submitted())
    assert cancel.action is BrokerAction.CANCEL
    assert cancel.as_dict() == {"variety": "regular", "order_id": "BRK-1"}

    assert_raises(ValueError, lambda: ZerodhaOrderMapper.modify_request(order(), modify_command()))
    assert_raises(ValueError, lambda: ZerodhaOrderMapper.modify_request(order(status=OrderStatus.SUBMITTED), modify_command()))
    assert_raises(ValueError, lambda: ZerodhaOrderMapper.modify_request(submitted(status=OrderStatus.CANCELLED), modify_command()))
    assert_raises(ValueError, lambda: ZerodhaOrderMapper.modify_request(submitted(), OrderCommand(OrderCommandType.FILL, "order-1", TS)))
    assert_raises(ValueError, lambda: ZerodhaOrderMapper.cancel_request(order()))
    assert_raises(ValueError, lambda: ZerodhaOrderMapper.cancel_request(order(status=OrderStatus.SUBMITTED)))
    assert_raises(ValueError, lambda: ZerodhaOrderMapper.cancel_request(submitted(status=OrderStatus.FILLED)))


def test_dry_run_never_calls_client_and_returns_payload_without_fake_id():
    client = FakeClient()
    adapter = ZerodhaBrokerAdapter(client=client)
    place = adapter.place(order())
    modify = adapter.modify(submitted(), modify_command())
    cancel = adapter.cancel(submitted())

    assert client.calls == []
    assert place.status is BrokerResultStatus.DRY_RUN
    assert modify.status is BrokerResultStatus.DRY_RUN
    assert cancel.status is BrokerResultStatus.DRY_RUN
    assert place.broker_order_id is None
    assert modify.broker_order_id is None
    assert cancel.broker_order_id is None
    assert place.error_message is None
    assert place.request.as_dict()["tradingsymbol"] == "NIFTY"
    assert modify.request.as_dict()["quantity"] == 120
    assert cancel.request.as_dict()["order_id"] == "BRK-1"


def test_client_mode_calls_fake_client_and_validates_results():
    place_client = FakeClient("BRK-NEW")
    place = ZerodhaBrokerAdapter(place_client, BrokerExecutionMode.CLIENT).place(order())
    assert place.status is BrokerResultStatus.ACCEPTED
    assert place.broker_order_id == "BRK-NEW"
    assert len(place_client.calls) == 1
    assert place_client.calls[0][0] == "place"

    modify_client = FakeClient("BRK-1")
    modify = ZerodhaBrokerAdapter(modify_client, BrokerExecutionMode.CLIENT).modify(submitted(), modify_command())
    assert modify.status is BrokerResultStatus.ACCEPTED
    assert modify.broker_order_id == "BRK-1"
    assert modify_client.calls[0][0] == "modify"

    cancel_client = FakeClient("BRK-1")
    cancel = ZerodhaBrokerAdapter(cancel_client, BrokerExecutionMode.CLIENT).cancel(submitted())
    assert cancel.status is BrokerResultStatus.ACCEPTED
    assert cancel.broker_order_id == "BRK-1"
    assert cancel_client.calls[0][0] == "cancel"

    assert ZerodhaBrokerAdapter(FakeClient(""), BrokerExecutionMode.CLIENT).place(order()).status is BrokerResultStatus.FAILED
    assert ZerodhaBrokerAdapter(FakeClient("OTHER"), BrokerExecutionMode.CLIENT).modify(submitted(), modify_command()).status is BrokerResultStatus.FAILED
    assert ZerodhaBrokerAdapter(FakeClient("OTHER"), BrokerExecutionMode.CLIENT).cancel(submitted()).status is BrokerResultStatus.FAILED
    assert ZerodhaBrokerAdapter(FakeClient(raise_error=True), BrokerExecutionMode.CLIENT).place(order()).status is BrokerResultStatus.FAILED
    assert_raises(ValueError, lambda: ZerodhaBrokerAdapter(FakeClient(), BrokerExecutionMode.CLIENT).place(submitted()))


def test_response_parsing_valid_payloads_unknowns_and_validation():
    opened = ZerodhaResponseParser.parse_order_update(
        {
            "order_id": " BRK-1 ",
            "status": "OPEN",
            "order_timestamp": "2026-07-10T10:01:00",
            "filled_quantity": 0,
            "pending_quantity": 150,
            "average_price": 0,
            "status_message": " ",
        }
    )
    assert opened.order_id == "BRK-1"
    assert opened.status is ZerodhaOrderStatus.OPEN
    assert opened.timestamp == datetime(2026, 7, 10, 10, 1)
    assert opened.status_message is None

    complete = ZerodhaResponseParser.parse_order_update(
        {
            "order_id": "BRK-1",
            "status": "COMPLETE",
            "exchange_update_timestamp": TS,
            "filled_quantity": 150,
            "pending_quantity": 0,
            "average_price": 100.25,
        }
    )
    assert complete.status is ZerodhaOrderStatus.COMPLETE

    cancelled = ZerodhaResponseParser.parse_order_update(
        {"order_id": "BRK-1", "status": "CANCELLED", "order_timestamp": TS, "filled_quantity": 0, "pending_quantity": 150, "average_price": 0.0}
    )
    rejected = ZerodhaResponseParser.parse_order_update(
        {"order_id": "BRK-1", "status": "REJECTED", "order_timestamp": TS, "filled_quantity": 0, "pending_quantity": 150, "average_price": 0.0, "status_message": "RMS"}
    )
    unknown = ZerodhaResponseParser.parse_order_update(
        {"order_id": "BRK-1", "status": "WEIRD", "order_timestamp": TS, "filled_quantity": 0, "pending_quantity": 150, "average_price": 0.0}
    )
    assert cancelled.status is ZerodhaOrderStatus.CANCELLED
    assert rejected.status is ZerodhaOrderStatus.REJECTED
    assert unknown.status is ZerodhaOrderStatus.UNKNOWN

    bad_payloads = [
        {"status": "OPEN", "order_timestamp": TS, "filled_quantity": 0, "pending_quantity": 150, "average_price": 0.0},
        {"order_id": "BRK-1", "status": "OPEN", "order_timestamp": TS, "filled_quantity": -1, "pending_quantity": 150, "average_price": 0.0},
        {"order_id": "BRK-1", "status": "OPEN", "order_timestamp": "bad", "filled_quantity": 0, "pending_quantity": 150, "average_price": 0.0},
        {"order_id": "BRK-1", "status": "OPEN", "order_timestamp": TS, "filled_quantity": 0, "pending_quantity": 150, "average_price": float("nan")},
    ]
    for payload in bad_payloads:
        assert_raises((TypeError, ValueError), lambda payload=payload: ZerodhaResponseParser.parse_order_update(payload))


def test_command_translation_acknowledgement_fills_cancel_reject_and_unknowns():
    pending = order()
    acknowledged = ZerodhaResponseParser.to_order_command(pending, update(status=ZerodhaOrderStatus.OPEN))
    assert acknowledged.command_type is OrderCommandType.ACKNOWLEDGE
    assert acknowledged.broker_order_id == "BRK-1"

    submitted_order = submitted()
    assert ZerodhaResponseParser.to_order_command(submitted_order, update(status=ZerodhaOrderStatus.OPEN)) is None
    assert ZerodhaResponseParser.to_order_command(submitted_order, update(status=ZerodhaOrderStatus.MODIFIED)) is None
    assert ZerodhaResponseParser.to_order_command(submitted_order, update(status=ZerodhaOrderStatus.UNKNOWN)) is None

    partial = ZerodhaResponseParser.to_order_command(submitted_order, update(filled_quantity=25, pending_quantity=125, average_price=100.5))
    assert partial.command_type is OrderCommandType.FILL
    assert partial.fill_quantity == 25
    assert partial.fill_price == 100.5

    previous_partial = submitted(filled_quantity=25, remaining_quantity=125, average_fill_price=100.5, status=OrderStatus.PARTIALLY_FILLED)
    assert ZerodhaResponseParser.to_order_command(previous_partial, update(filled_quantity=25, pending_quantity=125, average_price=100.5)) is None
    increased = ZerodhaResponseParser.to_order_command(previous_partial, update(filled_quantity=50, pending_quantity=100, average_price=101.0))
    assert increased.fill_quantity == 25
    assert increased.fill_price == 101.5
    assert_raises(ValueError, lambda: ZerodhaResponseParser.to_order_command(previous_partial, update(filled_quantity=10, pending_quantity=140, average_price=100.0)))

    complete = ZerodhaResponseParser.to_order_command(previous_partial, update(status=ZerodhaOrderStatus.COMPLETE, filled_quantity=150, pending_quantity=0, average_price=101.0))
    assert complete.command_type is OrderCommandType.FILL
    assert complete.fill_quantity == 125
    assert complete.fill_price == 101.1
    filled = submitted(status=OrderStatus.FILLED, filled_quantity=150, remaining_quantity=0, average_fill_price=101.0)
    assert ZerodhaResponseParser.to_order_command(filled, update(status=ZerodhaOrderStatus.COMPLETE, filled_quantity=150, pending_quantity=0, average_price=101.0)) is None
    assert_raises(ValueError, lambda: ZerodhaResponseParser.to_order_command(submitted_order, update(status=ZerodhaOrderStatus.COMPLETE, filled_quantity=149, pending_quantity=1, average_price=101.0)))
    assert_raises(ValueError, lambda: ZerodhaResponseParser.to_order_command(submitted_order, update(filled_quantity=151, pending_quantity=0, average_price=101.0)))

    cancel = ZerodhaResponseParser.to_order_command(submitted_order, update(status=ZerodhaOrderStatus.CANCELLED))
    assert cancel.command_type is OrderCommandType.CANCEL
    assert ZerodhaResponseParser.to_order_command(submitted(status=OrderStatus.CANCELLED), update(status=ZerodhaOrderStatus.CANCELLED)) is None

    reject = ZerodhaResponseParser.to_order_command(submitted_order, update(status=ZerodhaOrderStatus.REJECTED, status_message="RMS block"))
    assert reject.command_type is OrderCommandType.REJECT
    assert reject.rejection_message == "RMS block"
    fallback = ZerodhaResponseParser.to_order_command(submitted_order, update(status=ZerodhaOrderStatus.REJECTED))
    assert fallback.rejection_message == "Broker rejected order"


def test_cumulative_average_derives_incremental_fill_prices_for_order_management():
    engine = OrderManagementEngine(EventBus(), "NIFTY", "1m")
    state = submitted(quantity=100, remaining_quantity=100)
    engine._orders[state.client_order_id] = state
    engine._latest_order_id = state.client_order_id
    engine._data = state
    engine._approved_quantities[state.client_order_id] = 100
    engine._timestamp_is_aware = False

    first = ZerodhaResponseParser.to_order_command(
        state,
        update(filled_quantity=25, pending_quantity=75, average_price=100.0),
    )
    assert first.fill_quantity == 25
    assert first.fill_price == 100.0
    after_first = engine.apply(first)
    assert after_first.average_fill_price == 100.0

    second = ZerodhaResponseParser.to_order_command(
        after_first,
        update(filled_quantity=50, pending_quantity=50, average_price=102.0),
    )
    assert second.fill_quantity == 25
    assert second.fill_price == 104.0
    after_second = engine.apply(second)
    assert after_second.average_fill_price == 102.0

    third = ZerodhaResponseParser.to_order_command(
        after_second,
        update(filled_quantity=75, pending_quantity=25, average_price=103.0),
    )
    assert third.fill_quantity == 25
    assert third.fill_price == 105.0
    after_third = engine.apply(third)
    assert after_third.average_fill_price == 103.0

    assert ZerodhaResponseParser.to_order_command(
        after_third,
        update(filled_quantity=75, pending_quantity=25, average_price=103.0),
    ) is None

    complete = ZerodhaResponseParser.to_order_command(
        after_third,
        update(status=ZerodhaOrderStatus.COMPLETE, filled_quantity=100, pending_quantity=0, average_price=104.0),
    )
    assert complete.fill_quantity == 25
    assert complete.fill_price == 107.0
    filled = engine.apply(complete)
    assert filled.status is OrderStatus.FILLED
    assert filled.average_fill_price == 104.0


def test_invalid_cumulative_average_fill_updates_are_rejected():
    submitted_order = submitted()
    assert_raises(
        ValueError,
        lambda: ZerodhaResponseParser.to_order_command(
            submitted_order,
            update(filled_quantity=25, pending_quantity=125, average_price=0.0),
        ),
    )
    previous_partial = submitted(filled_quantity=25, remaining_quantity=125, average_fill_price=100.0, status=OrderStatus.PARTIALLY_FILLED)
    assert_raises(
        ValueError,
        lambda: ZerodhaResponseParser.to_order_command(
            previous_partial,
            update(filled_quantity=50, pending_quantity=100, average_price=50.0),
        ),
    )
    missing_previous_average = submitted(
        filled_quantity=25,
        remaining_quantity=125,
        average_fill_price=None,
        status=OrderStatus.PARTIALLY_FILLED,
    )
    assert_raises(
        ValueError,
        lambda: ZerodhaResponseParser.to_order_command(
            missing_previous_average,
            update(filled_quantity=50, pending_quantity=100, average_price=101.0),
        ),
    )


def test_architecture_no_events_no_credentials_no_network_and_immutability():
    class RecordingBus:
        def __init__(self):
            self.events = []

        def publish(self, *args):
            self.events.append(args)

    bus = RecordingBus()
    adapter = ZerodhaBrokerAdapter()
    state = order()
    result = adapter.place(state)
    assert result.status is BrokerResultStatus.DRY_RUN
    assert bus.events == []
    assert state.status is OrderStatus.PENDING_SUBMISSION
    assert not hasattr(adapter, "api_key")
    assert not hasattr(adapter, "api_secret")
    assert not hasattr(adapter, "access_token")
    assert not hasattr(adapter, "login")
    assert not hasattr(adapter, "connect")
    assert not hasattr(adapter, "ticker")
    assert FakeClient("BRK-1").calls == []
