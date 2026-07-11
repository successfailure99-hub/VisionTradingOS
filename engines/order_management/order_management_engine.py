"""
Order Management Engine V1.
"""

from dataclasses import replace

from core.base_engine import BaseEngine
from core.events import ORDER_CANCELLED, ORDER_FILLED, ORDER_MODIFIED, ORDER_PLACED, ORDER_REJECTED
from engines.order_management.enums import (
    OrderCommandType,
    OrderRejectionReason,
    OrderStatus,
)
from engines.order_management.models import OrderCommand, OrderSnapshot, OrderState
from engines.order_management.validator import OrderValidator


class OrderManagementEngine(BaseEngine):
    """
    Broker-independent internal order lifecycle manager.

    Order Management Engine V1 consumes Risk-approved order snapshots and
    explicit lifecycle commands, then manages immutable internal order
    states. It does not place real orders, call broker APIs, select
    strikes, fetch prices, retry submissions, maintain positions,
    calculate P&L, persist orders, or execute trades. Broker adapters will
    later translate these states into actual API calls. Risk approval is
    mandatory, quantity cannot exceed the Risk-approved quantity, and
    calls are expected to be serialized and single-threaded.
    """

    def __init__(self, event_bus, symbol: str, timeframe: str):
        super().__init__(event_bus)
        self._symbol = OrderValidator.normalize_symbol(symbol)
        self._timeframe = OrderValidator.normalize_timeframe(timeframe)
        self._orders: dict[str, OrderState] = {}
        self._latest_order_id: str | None = None
        self._timestamp_is_aware: bool | None = None
        self._latest_commands: dict[str, OrderCommand] = {}
        self._broker_order_ids: dict[str, str] = {}
        self._approved_quantities: dict[str, int] = {}

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def latest_order(self) -> OrderState | None:
        if self._latest_order_id is None:
            return None
        return self._orders[self._latest_order_id]

    @property
    def order_count(self) -> int:
        return len(self._orders)

    def create(self, snapshot: OrderSnapshot) -> OrderState:
        canonical, is_aware = OrderValidator.validate_creation_snapshot(
            snapshot,
            self._symbol,
            self._timeframe,
            self._timestamp_is_aware,
        )
        request = canonical.request
        risk = canonical.risk
        if request.client_order_id in self._orders:
            raise ValueError(OrderRejectionReason.DUPLICATE_ORDER_ID.value)

        state = OrderState(
            client_order_id=request.client_order_id,
            broker_order_id=None,
            symbol=canonical.symbol,
            exchange=request.exchange,
            timeframe=canonical.timeframe,
            created_at=canonical.timestamp,
            updated_at=canonical.timestamp,
            side=request.side,
            order_type=request.order_type,
            product_type=request.product_type,
            status=OrderStatus.PENDING_SUBMISSION,
            quantity=request.quantity,
            filled_quantity=0,
            remaining_quantity=request.quantity,
            average_fill_price=None,
            limit_price=request.limit_price,
            trigger_price=request.trigger_price,
            risk_entry_price=risk.entry_price,
            risk_stop_price=risk.stop_price,
            risk_target_price=risk.target_price,
            estimated_risk_amount=risk.estimated_risk_amount,
            rejection_reason=OrderRejectionReason.NONE,
            rejection_message=None,
            version=1,
        )
        if self._timestamp_is_aware is None:
            self._timestamp_is_aware = is_aware
        self._store(state)
        self._event_bus.publish(ORDER_PLACED, state)
        return state

    def apply(self, command: OrderCommand) -> OrderState:
        client_order_id = self._command_order_id(command)
        state = self._orders.get(client_order_id)
        if state is None:
            raise ValueError("Unknown client_order_id.")
        if command == self._latest_commands.get(client_order_id):
            return state
        if (
            command.command_type is OrderCommandType.ACKNOWLEDGE
            and state.status is OrderStatus.SUBMITTED
            and command.broker_order_id == state.broker_order_id
        ):
            return state

        canonical = OrderValidator.validate_command(command, state, self._timestamp_is_aware)
        if canonical.command_type is OrderCommandType.ACKNOWLEDGE:
            return self._acknowledge(state, canonical)
        if canonical.command_type is OrderCommandType.MODIFY:
            return self._modify(state, canonical)
        if canonical.command_type is OrderCommandType.FILL:
            return self._fill(state, canonical)
        if canonical.command_type is OrderCommandType.CANCEL:
            return self._cancel(state, canonical)
        if canonical.command_type is OrderCommandType.REJECT:
            return self._reject(state, canonical)
        raise ValueError(OrderRejectionReason.INVALID_TRANSITION.value)

    def get_order(self, client_order_id: str) -> OrderState | None:
        if not isinstance(client_order_id, str):
            return None
        return self._orders.get(client_order_id.strip())

    def get_orders(self) -> tuple[OrderState, ...]:
        return tuple(self._orders.values())

    def reset(self) -> None:
        super().clear()
        self._orders.clear()
        self._latest_order_id = None
        self._timestamp_is_aware = None
        self._latest_commands.clear()
        self._broker_order_ids.clear()
        self._approved_quantities.clear()

    def clear(self) -> None:
        self.reset()

    def _acknowledge(self, state: OrderState, command: OrderCommand) -> OrderState:
        broker_order_id = command.broker_order_id
        if not isinstance(broker_order_id, str) or not broker_order_id:
            raise ValueError("broker_order_id is required.")
        owner = self._broker_order_ids.get(broker_order_id)
        if owner is not None and owner != state.client_order_id:
            raise ValueError(OrderRejectionReason.DUPLICATE_ORDER_ID.value)
        if state.broker_order_id is not None:
            if state.broker_order_id == broker_order_id:
                return self._remember_duplicate(state, command)
            raise ValueError(OrderRejectionReason.INVALID_TRANSITION.value)
        new_state = replace(
            state,
            broker_order_id=broker_order_id,
            status=OrderStatus.SUBMITTED,
            updated_at=command.timestamp,
            version=state.version + 1,
        )
        self._broker_order_ids[broker_order_id] = state.client_order_id
        self._store_transition(new_state, command, ORDER_PLACED)
        return new_state

    def _modify(self, state: OrderState, command: OrderCommand) -> OrderState:
        supplied = [
            command.new_quantity is not None,
            command.new_limit_price is not None,
            command.new_trigger_price is not None,
        ]
        if not any(supplied):
            raise ValueError("At least one modifiable field is required.")
        quantity = state.quantity
        limit_price = state.limit_price
        trigger_price = state.trigger_price
        if command.new_quantity is not None:
            quantity = OrderValidator._positive_int("new_quantity", command.new_quantity)
            if quantity < state.filled_quantity:
                raise ValueError("new_quantity cannot be below filled quantity.")
            if quantity > self._approved_quantities[state.client_order_id]:
                raise ValueError("new_quantity cannot exceed Risk-approved quantity.")
        if command.new_limit_price is not None:
            limit_price = OrderValidator._optional_positive_real("new_limit_price", command.new_limit_price)
        if command.new_trigger_price is not None:
            trigger_price = OrderValidator._optional_positive_real("new_trigger_price", command.new_trigger_price)
        OrderValidator.validate_order_type_fields(
            state.order_type,
            state.side,
            limit_price,
            trigger_price,
            state.risk_entry_price,
        )
        remaining = quantity - state.filled_quantity
        if (
            quantity == state.quantity
            and limit_price == state.limit_price
            and trigger_price == state.trigger_price
        ):
            return self._remember_duplicate(state, command)
        new_state = replace(
            state,
            updated_at=command.timestamp,
            quantity=quantity,
            remaining_quantity=remaining,
            limit_price=limit_price,
            trigger_price=trigger_price,
            version=state.version + 1,
        )
        self._store_transition(new_state, command, ORDER_MODIFIED)
        return new_state

    def _fill(self, state: OrderState, command: OrderCommand) -> OrderState:
        fill_quantity = OrderValidator._positive_int("fill_quantity", command.fill_quantity)
        fill_price = OrderValidator._optional_positive_real("fill_price", command.fill_price)
        if fill_price is None:
            raise ValueError("fill_price is required.")
        if fill_quantity > state.remaining_quantity:
            raise ValueError(OrderRejectionReason.OVERFILL.value)
        new_filled = state.filled_quantity + fill_quantity
        new_remaining = state.quantity - new_filled
        previous_average = state.average_fill_price or 0.0
        average = round(
            ((previous_average * state.filled_quantity) + (fill_price * fill_quantity)) / new_filled,
            4,
        )
        status = OrderStatus.PARTIALLY_FILLED if new_remaining > 0 else OrderStatus.FILLED
        new_state = replace(
            state,
            updated_at=command.timestamp,
            status=status,
            filled_quantity=new_filled,
            remaining_quantity=new_remaining,
            average_fill_price=average,
            version=state.version + 1,
        )
        self._store_transition(new_state, command, ORDER_FILLED)
        return new_state

    def _cancel(self, state: OrderState, command: OrderCommand) -> OrderState:
        new_state = replace(
            state,
            updated_at=command.timestamp,
            status=OrderStatus.CANCELLED,
            version=state.version + 1,
        )
        self._store_transition(new_state, command, ORDER_CANCELLED)
        return new_state

    def _reject(self, state: OrderState, command: OrderCommand) -> OrderState:
        if not isinstance(command.rejection_message, str) or not command.rejection_message:
            raise ValueError("rejection_message is required.")
        new_state = replace(
            state,
            updated_at=command.timestamp,
            status=OrderStatus.REJECTED,
            rejection_reason=OrderRejectionReason.BROKER_REJECTED,
            rejection_message=command.rejection_message,
            version=state.version + 1,
        )
        self._store_transition(new_state, command, ORDER_REJECTED)
        return new_state

    def _store(self, state: OrderState) -> None:
        self._orders[state.client_order_id] = state
        self._approved_quantities.setdefault(state.client_order_id, state.quantity)
        self._latest_order_id = state.client_order_id
        self._data = state

    def _store_transition(self, state: OrderState, command: OrderCommand, event_name: str) -> None:
        self._store(state)
        self._latest_commands[state.client_order_id] = command
        self._event_bus.publish(event_name, state)

    def _remember_duplicate(self, state: OrderState, command: OrderCommand) -> OrderState:
        self._latest_commands[state.client_order_id] = command
        return state

    @staticmethod
    def _command_order_id(command: OrderCommand) -> str:
        if not isinstance(command, OrderCommand):
            raise TypeError("command must be an OrderCommand.")
        if not isinstance(command.client_order_id, str) or not command.client_order_id.strip():
            raise ValueError("client_order_id cannot be empty.")
        return command.client_order_id.strip()
