"""
Tests for Order Management Engine V1.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from core.event_bus import EventBus
from core.events import ORDER_CANCELLED, ORDER_FILLED, ORDER_MODIFIED, ORDER_PLACED, ORDER_REJECTED
from engines.ai_reasoning.enums import ReasoningConfidence, TradingSuitability
from engines.market_context.enums import MarketBias, MarketPhase
from engines.order_management import (
    OrderCommand,
    OrderCommandType,
    OrderManagementEngine,
    OrderRejectionReason,
    OrderRequest,
    OrderSide,
    OrderSnapshot,
    OrderState,
    OrderStatus,
    OrderType,
    OrderValidator,
    ProductType,
)
from engines.risk.enums import RiskDecision, RiskRejectionReason, RiskReductionReason, RiskTier
from engines.risk.models import RiskDecisionState
from engines.strategy.enums import (
    BlockReason,
    EntryReference,
    SetupQuality,
    StopReference,
    StrategyDecision,
    TargetReference,
    TradeDirection,
)
from engines.strategy.models import StrategyDecisionState


TS = datetime(2026, 7, 10, 10, 0)


def assert_raises(expected_error, callback):
    try:
        callback()
    except expected_error:
        return
    raise AssertionError(f"Expected {expected_error}")


def strategy(direction=TradeDirection.BULLISH, timestamp=TS):
    return StrategyDecisionState(
        symbol="NIFTY",
        timeframe="1m",
        timestamp=timestamp,
        decision=StrategyDecision.TRADE_ELIGIBLE,
        direction=direction,
        setup_quality=SetupQuality.HIGH,
        entry_reference=EntryReference.PRICE_ACTION_RETEST,
        stop_reference=StopReference.LATEST_SWING,
        target_reference=TargetReference.CAMARILLA_LEVEL,
        block_reason=BlockReason.NONE,
        market_bias=MarketBias.BULLISH,
        market_phase=MarketPhase.TRENDING_UP,
        confidence=ReasoningConfidence.HIGH,
        trading_suitability=TradingSuitability.SUITABLE,
        rationale=("strategy",),
    )


def risk(**overrides):
    values = {
        "symbol": "NIFTY",
        "timeframe": "1m",
        "timestamp": TS,
        "decision": RiskDecision.APPROVED,
        "risk_tier": RiskTier.STANDARD,
        "rejection_reason": RiskRejectionReason.NONE,
        "reduction_reason": RiskReductionReason.NONE,
        "direction": TradeDirection.BULLISH,
        "account_equity": 100000.0,
        "realized_pnl_today": 0.0,
        "daily_loss_limit_amount": 5000.0,
        "remaining_daily_loss_capacity": 5000.0,
        "applied_risk_percent": 2.0,
        "risk_budget": 2000.0,
        "entry_price": 100.0,
        "stop_price": 90.0,
        "target_price": 120.0,
        "stop_distance": 10.0,
        "target_distance": 20.0,
        "reward_risk_ratio": 2.0,
        "lot_size": 75,
        "requested_lots": 2,
        "maximum_permitted_lots": 2,
        "approved_lots": 2,
        "approved_quantity": 150,
        "estimated_risk_amount": 1500.0,
        "estimated_reward_amount": 3000.0,
        "rationale": ("approved",),
    }
    values.update(overrides)
    return RiskDecisionState(**values)


def request(**overrides):
    values = {
        "client_order_id": " order-1 ",
        "symbol": " nifty ",
        "exchange": " nse ",
        "timeframe": " 1m ",
        "timestamp": TS,
        "side": OrderSide.BUY,
        "order_type": OrderType.MARKET,
        "product_type": ProductType.INTRADAY,
        "quantity": 150,
        "limit_price": None,
        "trigger_price": None,
    }
    values.update(overrides)
    return OrderRequest(**values)


def snapshot(**overrides):
    values = {
        "symbol": " nifty ",
        "timeframe": " 1m ",
        "timestamp": TS,
        "risk": risk(),
        "request": request(),
    }
    values.update(overrides)
    return OrderSnapshot(**values)


def engine(symbol=" nifty ", timeframe=" 1m "):
    return OrderManagementEngine(EventBus(), symbol, timeframe)


def create_order(order_engine=None, order_snapshot=None):
    return (order_engine or engine()).create(order_snapshot or snapshot())


def command(command_type, minutes=1, **overrides):
    values = {
        "command_type": command_type,
        "client_order_id": "order-1",
        "timestamp": TS + timedelta(minutes=minutes),
    }
    values.update(overrides)
    return OrderCommand(**values)


def assert_atomic_rejection(order_engine, callback):
    old_orders = order_engine.get_orders()
    old_latest = order_engine.latest_order
    old_data = order_engine.data
    old_ready = order_engine.is_ready()
    events = []
    for event_name in (ORDER_PLACED, ORDER_MODIFIED, ORDER_CANCELLED, ORDER_FILLED, ORDER_REJECTED):
        order_engine._event_bus.subscribe(event_name, events.append)
    assert_raises((TypeError, ValueError), callback)
    assert order_engine.get_orders() == old_orders
    assert order_engine.latest_order == old_latest
    assert order_engine.data == old_data
    assert order_engine.is_ready() == old_ready
    assert events == []


def test_enum_values_models_slots_exports_and_request_normalization():
    assert OrderSide.BUY.value == "buy"
    assert OrderType.STOP_LIMIT.value == "stop_limit"
    assert ProductType.INTRADAY.value == "intraday"
    assert OrderStatus.PENDING_SUBMISSION.value == "pending_submission"
    assert OrderCommandType.ACKNOWLEDGE.value == "acknowledge"
    assert OrderRejectionReason.OVERFILL.value == "overfill"

    req = request()
    snap = snapshot(request=req)
    state = create_order(order_snapshot=snap)
    assert req.client_order_id == "order-1"
    assert req.symbol == "NIFTY"
    assert req.exchange == "NSE"
    assert req.timeframe == "1m"
    assert isinstance(state, OrderState)
    assert not hasattr(req, "__dict__")
    assert not hasattr(state, "__dict__")
    assert_raises(FrozenInstanceError, lambda: setattr(req, "quantity", 1))
    assert_raises(FrozenInstanceError, lambda: setattr(state, "status", OrderStatus.FILLED))

    from engines.order_management import __all__

    assert __all__ == [
        "OrderManagementEngine",
        "OrderValidator",
        "OrderRequest",
        "OrderCommand",
        "OrderSnapshot",
        "OrderState",
        "OrderSide",
        "OrderType",
        "ProductType",
        "OrderStatus",
        "OrderCommandType",
        "OrderRejectionReason",
    ]
    assert isinstance(OrderValidator(), OrderValidator)


def test_constructor_normalization_initial_state_and_invalid_context():
    order_engine = engine()
    assert order_engine.symbol == "NIFTY"
    assert order_engine.timeframe == "1m"
    assert order_engine.latest_order is None
    assert order_engine.order_count == 0
    assert order_engine.data is None
    assert not order_engine.is_ready()
    assert_raises(ValueError, lambda: OrderManagementEngine(EventBus(), "", "1m"))
    assert_raises(ValueError, lambda: OrderManagementEngine(EventBus(), "NIFTY", " "))


def test_creation_validation_rejects_bad_snapshot_risk_context_and_timestamps():
    order_engine = engine()
    bad_risk = risk(symbol="BANKNIFTY")
    cases = [
        lambda: order_engine.create("bad"),
        lambda: order_engine.create(snapshot(risk="bad")),
        lambda: order_engine.create(snapshot(symbol="BANKNIFTY")),
        lambda: order_engine.create(snapshot(timeframe="5m")),
        lambda: order_engine.create(snapshot(timestamp="bad")),
        lambda: order_engine.create(snapshot(risk=bad_risk)),
        lambda: order_engine.create(snapshot(risk=risk(timeframe="5m"))),
        lambda: order_engine.create(snapshot(risk=risk(timestamp=TS + timedelta(minutes=1)))),
        lambda: order_engine.create(snapshot(request=request(timestamp=TS + timedelta(minutes=1)))),
        lambda: order_engine.create(snapshot(request=request(symbol="BANKNIFTY"))),
        lambda: order_engine.create(snapshot(request=request(timeframe="5m"))),
    ]
    for case in cases:
        assert_atomic_rejection(order_engine, case)


def test_risk_and_request_consistency_validation():
    order_engine = engine()
    rejected_risk = risk(
        decision=RiskDecision.REJECTED,
        risk_tier=RiskTier.BLOCKED,
        rejection_reason=RiskRejectionReason.STRATEGY_NO_TRADE,
        approved_lots=0,
        approved_quantity=0,
    )
    cases = [
        lambda: order_engine.create(snapshot(risk=rejected_risk)),
        lambda: order_engine.create(snapshot(risk=risk(approved_quantity=0))),
        lambda: order_engine.create(snapshot(risk=risk(approved_lots=0))),
        lambda: order_engine.create(snapshot(risk=risk(direction=TradeDirection.NONE))),
        lambda: order_engine.create(snapshot(request=request(side=OrderSide.SELL))),
        lambda: order_engine.create(snapshot(request=request(quantity=75))),
        lambda: order_engine.create(snapshot(request=request(exchange=" "))),
        lambda: order_engine.create(snapshot(request=request(client_order_id=" "))),
        lambda: order_engine.create(snapshot(request=request(quantity=0))),
        lambda: order_engine.create(snapshot(request=request(quantity=True))),
        lambda: order_engine.create(snapshot(request=request(product_type="delivery"))),
    ]
    for case in cases:
        assert_atomic_rejection(order_engine, case)


def test_order_type_rules_for_market_limit_stop_market_and_stop_limit():
    create_order(order_snapshot=snapshot(request=request(order_type=OrderType.MARKET)))

    invalids = [
        request(order_type=OrderType.MARKET, limit_price=100.0),
        request(order_type=OrderType.LIMIT),
        request(order_type=OrderType.LIMIT, limit_price=101.0),
        request(order_type=OrderType.LIMIT, limit_price=100.0, trigger_price=99.0),
        request(order_type=OrderType.STOP_MARKET),
        request(order_type=OrderType.STOP_MARKET, trigger_price=101.0),
        request(order_type=OrderType.STOP_MARKET, limit_price=100.0, trigger_price=100.0),
        request(order_type=OrderType.STOP_LIMIT, limit_price=99.0, trigger_price=100.0),
    ]
    for bad in invalids:
        assert_atomic_rejection(engine(), lambda bad=bad: create_order(order_snapshot=snapshot(request=bad)))

    limit_state = create_order(order_snapshot=snapshot(request=request(order_type=OrderType.LIMIT, limit_price=100.0)))
    assert limit_state.limit_price == 100.0

    stop_market = create_order(
        order_snapshot=snapshot(
            request=request(client_order_id="order-2", order_type=OrderType.STOP_MARKET, trigger_price=100.0)
        )
    )
    assert stop_market.trigger_price == 100.0

    buy_stop_limit = create_order(
        order_snapshot=snapshot(
            request=request(client_order_id="order-3", order_type=OrderType.STOP_LIMIT, limit_price=101.0, trigger_price=100.0)
        )
    )
    assert buy_stop_limit.limit_price == 101.0

    bearish = risk(direction=TradeDirection.BEARISH)
    sell_stop_limit = create_order(
        order_snapshot=snapshot(
            risk=bearish,
            request=request(
                client_order_id="order-4",
                side=OrderSide.SELL,
                order_type=OrderType.STOP_LIMIT,
                limit_price=99.0,
                trigger_price=100.0,
            ),
        )
    )
    assert sell_stop_limit.side is OrderSide.SELL

    bad_sell = request(side=OrderSide.SELL, order_type=OrderType.STOP_LIMIT, limit_price=101.0, trigger_price=100.0)
    assert_atomic_rejection(engine(), lambda: create_order(order_snapshot=snapshot(risk=bearish, request=bad_sell)))


def test_creation_state_fields_events_multiple_orders_and_deterministic_ordering():
    order_engine = engine()
    events = []
    order_engine._event_bus.subscribe(
        ORDER_PLACED,
        lambda state: events.append((state, order_engine.data, order_engine.latest_order, order_engine.is_ready())),
    )
    state = order_engine.create(snapshot())
    assert state.status is OrderStatus.PENDING_SUBMISSION
    assert state.broker_order_id is None
    assert state.created_at == TS
    assert state.updated_at == TS
    assert state.quantity == 150
    assert state.filled_quantity == 0
    assert state.remaining_quantity == 150
    assert state.average_fill_price is None
    assert state.risk_entry_price == 100.0
    assert state.risk_stop_price == 90.0
    assert state.risk_target_price == 120.0
    assert state.estimated_risk_amount == 1500.0
    assert state.rejection_reason is OrderRejectionReason.NONE
    assert state.version == 1
    assert events == [(state, state, state, True)]

    second = order_engine.create(
        snapshot(
            request=request(client_order_id="order-2"),
        )
    )
    assert order_engine.order_count == 2
    assert order_engine.latest_order == second
    assert order_engine.data == second
    assert order_engine.get_orders() == (state, second)
    assert isinstance(order_engine.get_orders(), tuple)
    assert order_engine.get_order("missing") is None
    assert_atomic_rejection(order_engine, lambda: order_engine.create(snapshot()))


def test_acknowledgement_validation_duplicate_suppression_and_broker_id_uniqueness():
    order_engine = engine()
    state = create_order(order_engine)
    events = []
    order_engine._event_bus.subscribe(ORDER_PLACED, events.append)
    ack = command(OrderCommandType.ACKNOWLEDGE, broker_order_id="BRK-1")
    submitted = order_engine.apply(ack)
    assert submitted.status is OrderStatus.SUBMITTED
    assert submitted.broker_order_id == "BRK-1"
    assert submitted.version == state.version + 1
    assert events == [submitted]
    assert order_engine.apply(command(OrderCommandType.ACKNOWLEDGE, minutes=2, broker_order_id="BRK-1")) == submitted
    assert events == [submitted]
    assert_atomic_rejection(order_engine, lambda: order_engine.apply(command(OrderCommandType.ACKNOWLEDGE, minutes=2)))
    assert_atomic_rejection(order_engine, lambda: order_engine.apply(command(OrderCommandType.ACKNOWLEDGE, minutes=2, broker_order_id="BRK-2")))

    other = order_engine.create(snapshot(request=request(client_order_id="order-2")))
    assert other.status is OrderStatus.PENDING_SUBMISSION
    assert_atomic_rejection(
        order_engine,
        lambda: order_engine.apply(
            command(OrderCommandType.ACKNOWLEDGE, minutes=3, client_order_id="order-2", broker_order_id="BRK-1")
        ),
    )


def test_modification_from_pending_submitted_partial_and_validation_rules():
    order_engine = engine()
    state = create_order(order_engine)
    events = []
    order_engine._event_bus.subscribe(ORDER_MODIFIED, events.append)
    pending_modified = order_engine.apply(command(OrderCommandType.MODIFY, new_quantity=120))
    assert pending_modified.status is OrderStatus.PENDING_SUBMISSION
    assert pending_modified.quantity == 120
    assert pending_modified.remaining_quantity == 120
    assert events == [pending_modified]

    submitted = order_engine.apply(command(OrderCommandType.ACKNOWLEDGE, minutes=2, broker_order_id="BRK-1"))
    submitted_modified = order_engine.apply(command(OrderCommandType.MODIFY, minutes=3, new_quantity=150))
    assert submitted_modified.quantity == 150
    partial = order_engine.apply(command(OrderCommandType.FILL, minutes=4, fill_quantity=50, fill_price=100.0))
    partial_modified = order_engine.apply(command(OrderCommandType.MODIFY, minutes=5, new_quantity=100))
    assert partial_modified.status is OrderStatus.PARTIALLY_FILLED
    assert partial_modified.remaining_quantity == 50
    assert partial_modified.version == partial.version + 1

    assert order_engine.apply(command(OrderCommandType.MODIFY, minutes=6, new_quantity=100)) == partial_modified
    assert_atomic_rejection(order_engine, lambda: order_engine.apply(command(OrderCommandType.MODIFY, minutes=7)))
    assert_atomic_rejection(order_engine, lambda: order_engine.apply(command(OrderCommandType.MODIFY, minutes=7, new_quantity=49)))
    assert_atomic_rejection(order_engine, lambda: order_engine.apply(command(OrderCommandType.MODIFY, minutes=7, new_quantity=151)))
    assert_atomic_rejection(order_engine, lambda: order_engine.apply(command(OrderCommandType.MODIFY, minutes=7, new_limit_price=100.0)))


def test_modified_price_rules_for_limit_orders_and_terminal_modification_rejected():
    order_engine = engine()
    state = order_engine.create(snapshot(request=request(order_type=OrderType.LIMIT, limit_price=100.0)))
    submitted = order_engine.apply(command(OrderCommandType.ACKNOWLEDGE, broker_order_id="BRK-1"))
    assert submitted.status is OrderStatus.SUBMITTED
    assert order_engine.apply(command(OrderCommandType.MODIFY, minutes=2, new_limit_price=100.0)) == submitted
    assert_atomic_rejection(order_engine, lambda: order_engine.apply(command(OrderCommandType.MODIFY, minutes=2, new_limit_price=101.0)))
    filled = order_engine.apply(command(OrderCommandType.FILL, minutes=3, fill_quantity=150, fill_price=100.0))
    assert filled.status is OrderStatus.FILLED
    assert_atomic_rejection(order_engine, lambda: order_engine.apply(command(OrderCommandType.MODIFY, minutes=4, new_quantity=100)))
    assert state.status is OrderStatus.PENDING_SUBMISSION


def test_fill_partial_full_weighted_average_rounding_duplicates_and_rejections():
    order_engine = engine()
    create_order(order_engine)
    assert_atomic_rejection(order_engine, lambda: order_engine.apply(command(OrderCommandType.FILL, fill_quantity=1, fill_price=100.0)))
    order_engine.apply(command(OrderCommandType.ACKNOWLEDGE, broker_order_id="BRK-1"))
    events = []
    order_engine._event_bus.subscribe(ORDER_FILLED, events.append)
    first_fill = order_engine.apply(command(OrderCommandType.FILL, minutes=2, fill_quantity=50, fill_price=100.11111))
    assert first_fill.status is OrderStatus.PARTIALLY_FILLED
    assert first_fill.filled_quantity == 50
    assert first_fill.remaining_quantity == 100
    assert first_fill.average_fill_price == 100.1111
    duplicate = command(OrderCommandType.FILL, minutes=2, fill_quantity=50, fill_price=100.11111)
    assert order_engine.apply(duplicate) == first_fill
    assert events == [first_fill]
    full = order_engine.apply(command(OrderCommandType.FILL, minutes=3, fill_quantity=100, fill_price=101.22222))
    assert full.status is OrderStatus.FILLED
    assert full.filled_quantity == 150
    assert full.remaining_quantity == 0
    assert full.average_fill_price == 100.8518
    assert events == [first_fill, full]
    assert_atomic_rejection(order_engine, lambda: order_engine.apply(command(OrderCommandType.FILL, minutes=4, fill_quantity=1, fill_price=100.0)))

    for bad in [
        command(OrderCommandType.FILL, minutes=4, fill_quantity=0, fill_price=100.0),
        command(OrderCommandType.FILL, minutes=4, fill_quantity=1, fill_price=0.0),
    ]:
        fresh = engine()
        create_order(fresh)
        fresh.apply(command(OrderCommandType.ACKNOWLEDGE, broker_order_id="BRK-2"))
        assert_atomic_rejection(fresh, lambda bad=bad: fresh.apply(bad))

    cancelled = engine()
    create_order(cancelled)
    cancelled.apply(command(OrderCommandType.CANCEL))
    assert_atomic_rejection(cancelled, lambda: cancelled.apply(command(OrderCommandType.FILL, minutes=2, fill_quantity=1, fill_price=100.0)))

    rejected = engine()
    create_order(rejected)
    rejected.apply(command(OrderCommandType.REJECT, rejection_message="broker rejected"))
    assert_atomic_rejection(rejected, lambda: rejected.apply(command(OrderCommandType.FILL, minutes=2, fill_quantity=1, fill_price=100.0)))

    overfill = engine()
    create_order(overfill)
    overfill.apply(command(OrderCommandType.ACKNOWLEDGE, broker_order_id="BRK-3"))
    assert_atomic_rejection(overfill, lambda: overfill.apply(command(OrderCommandType.FILL, minutes=2, fill_quantity=151, fill_price=100.0)))


def test_cancel_pending_submitted_partial_duplicate_and_terminal_rejections():
    pending = engine()
    create_order(pending)
    events = []
    pending._event_bus.subscribe(ORDER_CANCELLED, events.append)
    cancelled = pending.apply(command(OrderCommandType.CANCEL))
    assert cancelled.status is OrderStatus.CANCELLED
    assert cancelled.filled_quantity == 0
    assert cancelled.remaining_quantity == 150
    assert pending.apply(command(OrderCommandType.CANCEL)) == cancelled
    assert events == [cancelled]
    assert_atomic_rejection(pending, lambda: pending.apply(command(OrderCommandType.CANCEL, minutes=2)))

    submitted_engine = engine()
    create_order(submitted_engine)
    submitted_engine.apply(command(OrderCommandType.ACKNOWLEDGE, broker_order_id="BRK-1"))
    assert submitted_engine.apply(command(OrderCommandType.CANCEL, minutes=2)).status is OrderStatus.CANCELLED

    partial_engine = engine()
    create_order(partial_engine)
    partial_engine.apply(command(OrderCommandType.ACKNOWLEDGE, broker_order_id="BRK-2"))
    partial_engine.apply(command(OrderCommandType.FILL, minutes=2, fill_quantity=25, fill_price=100.0))
    partial_cancelled = partial_engine.apply(command(OrderCommandType.CANCEL, minutes=3))
    assert partial_cancelled.filled_quantity == 25
    assert partial_cancelled.remaining_quantity == 125

    filled_engine = engine()
    create_order(filled_engine)
    filled_engine.apply(command(OrderCommandType.ACKNOWLEDGE, broker_order_id="BRK-3"))
    filled_engine.apply(command(OrderCommandType.FILL, minutes=2, fill_quantity=150, fill_price=100.0))
    assert_atomic_rejection(filled_engine, lambda: filled_engine.apply(command(OrderCommandType.CANCEL, minutes=3)))


def test_reject_pending_submitted_message_required_duplicate_and_partial_disallowed():
    order_engine = engine()
    create_order(order_engine)
    events = []
    order_engine._event_bus.subscribe(ORDER_REJECTED, events.append)
    rejected = order_engine.apply(command(OrderCommandType.REJECT, rejection_message=" broker rejected "))
    assert rejected.status is OrderStatus.REJECTED
    assert rejected.rejection_reason is OrderRejectionReason.BROKER_REJECTED
    assert rejected.rejection_message == "broker rejected"
    assert order_engine.apply(command(OrderCommandType.REJECT, rejection_message="broker rejected")) == rejected
    assert events == [rejected]
    assert_atomic_rejection(order_engine, lambda: order_engine.apply(command(OrderCommandType.REJECT, minutes=2, rejection_message="again")))

    submitted_engine = engine()
    create_order(submitted_engine)
    submitted_engine.apply(command(OrderCommandType.ACKNOWLEDGE, broker_order_id="BRK-1"))
    assert submitted_engine.apply(command(OrderCommandType.REJECT, minutes=2, rejection_message="no fill")).status is OrderStatus.REJECTED

    no_message = engine()
    create_order(no_message)
    assert_atomic_rejection(no_message, lambda: no_message.apply(command(OrderCommandType.REJECT)))

    partial_engine = engine()
    create_order(partial_engine)
    partial_engine.apply(command(OrderCommandType.ACKNOWLEDGE, broker_order_id="BRK-2"))
    partial_engine.apply(command(OrderCommandType.FILL, minutes=2, fill_quantity=1, fill_price=100.0))
    assert_atomic_rejection(partial_engine, lambda: partial_engine.apply(command(OrderCommandType.REJECT, minutes=3, rejection_message="late reject")))


def test_timestamp_rules_same_timestamp_and_independent_order_ordering():
    aware = engine()
    aware_ts = datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc)
    aware.create(
        snapshot(
            timestamp=aware_ts,
            risk=risk(timestamp=aware_ts),
            request=request(timestamp=aware_ts),
        )
    )
    assert_atomic_rejection(
        aware,
        lambda: aware.apply(
            OrderCommand(
                command_type=OrderCommandType.ACKNOWLEDGE,
                client_order_id="order-1",
                timestamp=TS,
                broker_order_id="BRK-1",
            )
        ),
    )

    order_engine = engine()
    create_order(order_engine)
    order_engine.apply(command(OrderCommandType.ACKNOWLEDGE, minutes=1, broker_order_id="BRK-1"))
    same_timestamp_fill = order_engine.apply(command(OrderCommandType.FILL, minutes=1, fill_quantity=1, fill_price=100.0))
    assert same_timestamp_fill.updated_at == TS + timedelta(minutes=1)
    assert_atomic_rejection(order_engine, lambda: order_engine.apply(command(OrderCommandType.MODIFY, minutes=0, new_quantity=100)))
    assert_atomic_rejection(
        order_engine,
        lambda: order_engine.apply(
            OrderCommand(command_type=OrderCommandType.MODIFY, client_order_id="order-1", timestamp="bad", new_quantity=100)
        ),
    )

    second = order_engine.create(snapshot(request=request(client_order_id="order-2")))
    assert second.updated_at == TS
    changed = order_engine.apply(
        command(OrderCommandType.MODIFY, minutes=0, client_order_id="order-2", new_quantity=100)
    )
    assert changed.client_order_id == "order-2"
    assert changed.updated_at == TS


def test_reset_clear_id_reuse_engine_independence_and_upstream_immutability():
    order_engine = engine()
    upstream_risk = risk()
    state = order_engine.create(snapshot(risk=upstream_risk))
    order_engine.apply(command(OrderCommandType.ACKNOWLEDGE, broker_order_id="BRK-1"))
    other = engine(symbol="BANKNIFTY")
    assert other.order_count == 0
    assert order_engine.order_count == 1
    assert state.version == 1
    assert upstream_risk.approved_quantity == 150

    order_engine.reset()
    assert order_engine.order_count == 0
    assert order_engine.latest_order is None
    assert order_engine.data is None
    assert not order_engine.is_ready()
    reused = order_engine.create(snapshot())
    assert reused.client_order_id == "order-1"
    order_engine.apply(command(OrderCommandType.ACKNOWLEDGE, broker_order_id="BRK-1"))
    order_engine.clear()
    assert order_engine.order_count == 0
    assert order_engine.latest_order is None
    assert not order_engine.is_ready()


def test_no_broker_or_network_dependency_surface():
    assert not hasattr(OrderManagementEngine, "place_order")
    assert not hasattr(OrderManagementEngine, "execute")
    assert not hasattr(OrderManagementEngine, "connect")
