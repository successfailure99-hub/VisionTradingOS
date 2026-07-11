"""
Stateless validation for Order Management Engine V1.
"""

from datetime import datetime
from math import isfinite
from numbers import Real

from engines.order_management.enums import (
    OrderCommandType,
    OrderRejectionReason,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
)
from engines.order_management.models import OrderCommand, OrderRequest, OrderSnapshot, OrderState
from engines.risk.enums import RiskDecision, RiskRejectionReason
from engines.risk.models import RiskDecisionState
from engines.strategy.enums import TradeDirection


class OrderValidator:
    """
    Stateless validator for broker-independent order lifecycle inputs.

    Order Management V1 validates internal order requests and lifecycle
    commands only. It does not publish events, cache state, mutate inputs,
    generate IDs, place orders, manage positions, calculate P&L, or access
    any broker. Risk approval is mandatory, and quantity cannot exceed the
    Risk-approved quantity. Calls are expected to be serialized and
    single-threaded by upstream orchestration.
    """

    TERMINAL_STATUSES = {
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
    }

    LEGAL_COMMANDS = {
        OrderStatus.PENDING_SUBMISSION: {
            OrderCommandType.ACKNOWLEDGE,
            OrderCommandType.MODIFY,
            OrderCommandType.CANCEL,
            OrderCommandType.REJECT,
        },
        OrderStatus.SUBMITTED: {
            OrderCommandType.MODIFY,
            OrderCommandType.FILL,
            OrderCommandType.CANCEL,
            OrderCommandType.REJECT,
        },
        OrderStatus.PARTIALLY_FILLED: {
            OrderCommandType.MODIFY,
            OrderCommandType.FILL,
            OrderCommandType.CANCEL,
        },
        OrderStatus.FILLED: set(),
        OrderStatus.CANCELLED: set(),
        OrderStatus.REJECTED: set(),
    }

    @classmethod
    def normalize_symbol(cls, symbol: str) -> str:
        if not isinstance(symbol, str):
            raise ValueError("symbol must be a string.")
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol cannot be empty.")
        return normalized

    @classmethod
    def normalize_timeframe(cls, timeframe: str) -> str:
        if not isinstance(timeframe, str):
            raise ValueError("timeframe must be a string.")
        normalized = timeframe.strip()
        if not normalized:
            raise ValueError("timeframe cannot be empty.")
        return normalized

    @classmethod
    def validate_request(cls, request: OrderRequest) -> OrderRequest:
        if not isinstance(request, OrderRequest):
            raise TypeError("request must be an OrderRequest.")
        if not request.client_order_id:
            raise ValueError("client_order_id cannot be empty.")
        symbol = cls.normalize_symbol(request.symbol)
        if not isinstance(request.exchange, str):
            raise ValueError("exchange must be a string.")
        exchange = request.exchange.strip().upper()
        if not exchange:
            raise ValueError("exchange cannot be empty.")
        timeframe = cls.normalize_timeframe(request.timeframe)
        if not isinstance(request.timestamp, datetime):
            raise ValueError("OrderRequest timestamp must be a datetime.")
        if not isinstance(request.side, OrderSide):
            raise ValueError("side must be an OrderSide.")
        if not isinstance(request.order_type, OrderType):
            raise ValueError("order_type must be an OrderType.")
        if request.product_type is not ProductType.INTRADAY:
            raise ValueError("V1 supports only intraday product type.")
        quantity = cls._positive_int("quantity", request.quantity)
        limit_price = cls._optional_positive_real("limit_price", request.limit_price)
        trigger_price = cls._optional_positive_real("trigger_price", request.trigger_price)
        return OrderRequest(
            client_order_id=request.client_order_id.strip(),
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            timestamp=request.timestamp,
            side=request.side,
            order_type=request.order_type,
            product_type=request.product_type,
            quantity=quantity,
            limit_price=limit_price,
            trigger_price=trigger_price,
        )

    @classmethod
    def validate_creation_snapshot(
        cls,
        snapshot: OrderSnapshot,
        symbol: str,
        timeframe: str,
        timestamp_is_aware: bool | None,
    ) -> tuple[OrderSnapshot, bool]:
        if not isinstance(snapshot, OrderSnapshot):
            raise TypeError("OrderManagementEngine expects an OrderSnapshot object.")
        context_symbol = cls.normalize_symbol(symbol)
        context_timeframe = cls.normalize_timeframe(timeframe)
        snapshot_symbol = cls.normalize_symbol(snapshot.symbol)
        snapshot_timeframe = cls.normalize_timeframe(snapshot.timeframe)
        if snapshot_symbol != context_symbol:
            raise ValueError("OrderSnapshot symbol does not match engine context.")
        if snapshot_timeframe != context_timeframe:
            raise ValueError("OrderSnapshot timeframe does not match engine context.")
        if not isinstance(snapshot.timestamp, datetime):
            raise ValueError("OrderSnapshot timestamp must be a datetime.")
        is_aware = snapshot.timestamp.tzinfo is not None
        if timestamp_is_aware is not None and is_aware != timestamp_is_aware:
            raise ValueError("OrderSnapshot timestamp timezone-awareness mode changed.")
        risk = cls._validate_risk(snapshot.risk, snapshot_symbol, snapshot_timeframe, snapshot.timestamp)
        request = cls.validate_request(snapshot.request)
        if request.symbol != snapshot_symbol:
            raise ValueError("OrderRequest symbol does not match snapshot.")
        if request.timeframe != snapshot_timeframe:
            raise ValueError("OrderRequest timeframe does not match snapshot.")
        if request.timestamp != snapshot.timestamp:
            raise ValueError("OrderRequest timestamp must match OrderSnapshot timestamp.")
        cls._validate_risk_consistency(risk, request)
        return OrderSnapshot(snapshot_symbol, snapshot_timeframe, snapshot.timestamp, risk, request), is_aware

    @classmethod
    def validate_command(cls, command: OrderCommand, state: OrderState, timestamp_is_aware: bool | None) -> OrderCommand:
        if not isinstance(command, OrderCommand):
            raise TypeError("command must be an OrderCommand.")
        if not isinstance(command.command_type, OrderCommandType):
            raise ValueError("command_type must be an OrderCommandType.")
        if command.command_type is OrderCommandType.CREATE:
            raise ValueError("CREATE commands are represented by OrderSnapshot.")
        if not isinstance(command.client_order_id, str) or not command.client_order_id.strip():
            raise ValueError("client_order_id cannot be empty.")
        if command.client_order_id.strip() != state.client_order_id:
            raise ValueError("OrderCommand client_order_id does not match order state.")
        if not isinstance(command.timestamp, datetime):
            raise ValueError("OrderCommand timestamp must be a datetime.")
        is_aware = command.timestamp.tzinfo is not None
        if timestamp_is_aware is not None and is_aware != timestamp_is_aware:
            raise ValueError("OrderCommand timestamp timezone-awareness mode changed.")
        if command.timestamp < state.updated_at:
            raise ValueError("Stale OrderCommand received.")
        if command.command_type not in cls.LEGAL_COMMANDS[state.status]:
            if state.status in cls.TERMINAL_STATUSES:
                raise ValueError(OrderRejectionReason.TERMINAL_ORDER.value)
            raise ValueError(OrderRejectionReason.INVALID_TRANSITION.value)
        return OrderCommand(
            command_type=command.command_type,
            client_order_id=command.client_order_id.strip(),
            timestamp=command.timestamp,
            broker_order_id=command.broker_order_id.strip() if isinstance(command.broker_order_id, str) else command.broker_order_id,
            new_quantity=command.new_quantity,
            new_limit_price=command.new_limit_price,
            new_trigger_price=command.new_trigger_price,
            fill_quantity=command.fill_quantity,
            fill_price=command.fill_price,
            rejection_message=command.rejection_message.strip()
            if isinstance(command.rejection_message, str)
            else command.rejection_message,
        )

    @classmethod
    def validate_order_type_fields(
        cls,
        order_type: OrderType,
        side: OrderSide,
        limit_price: float | None,
        trigger_price: float | None,
        risk_entry_price: float,
    ) -> None:
        if order_type is OrderType.MARKET:
            if limit_price is not None or trigger_price is not None:
                raise ValueError(OrderRejectionReason.INVALID_ORDER_TYPE_FIELDS.value)
            return
        if order_type is OrderType.LIMIT:
            if limit_price is None or trigger_price is not None:
                raise ValueError(OrderRejectionReason.INVALID_ORDER_TYPE_FIELDS.value)
            if limit_price != risk_entry_price:
                raise ValueError(OrderRejectionReason.PRICE_MISMATCH.value)
            return
        if order_type is OrderType.STOP_MARKET:
            if limit_price is not None or trigger_price is None:
                raise ValueError(OrderRejectionReason.INVALID_ORDER_TYPE_FIELDS.value)
            if trigger_price != risk_entry_price:
                raise ValueError(OrderRejectionReason.PRICE_MISMATCH.value)
            return
        if order_type is OrderType.STOP_LIMIT:
            if limit_price is None or trigger_price is None:
                raise ValueError(OrderRejectionReason.INVALID_ORDER_TYPE_FIELDS.value)
            if side is OrderSide.BUY and limit_price < trigger_price:
                raise ValueError(OrderRejectionReason.INVALID_ORDER_TYPE_FIELDS.value)
            if side is OrderSide.SELL and limit_price > trigger_price:
                raise ValueError(OrderRejectionReason.INVALID_ORDER_TYPE_FIELDS.value)
            if trigger_price != risk_entry_price:
                raise ValueError(OrderRejectionReason.PRICE_MISMATCH.value)
            return
        raise ValueError("Unsupported order type.")

    @classmethod
    def _validate_risk(
        cls,
        risk: RiskDecisionState,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
    ) -> RiskDecisionState:
        if not isinstance(risk, RiskDecisionState):
            raise ValueError("risk must be a RiskDecisionState.")
        if cls.normalize_symbol(risk.symbol) != symbol:
            raise ValueError("RiskDecisionState symbol does not match order context.")
        if cls.normalize_timeframe(risk.timeframe) != timeframe:
            raise ValueError("RiskDecisionState timeframe does not match order context.")
        if risk.timestamp != timestamp:
            raise ValueError("RiskDecisionState timestamp must match OrderSnapshot timestamp.")
        if risk.decision is not RiskDecision.APPROVED:
            raise ValueError(OrderRejectionReason.RISK_NOT_APPROVED.value)
        if risk.approved_quantity <= 0 or risk.approved_lots <= 0:
            raise ValueError(OrderRejectionReason.RISK_NOT_APPROVED.value)
        if risk.rejection_reason is not RiskRejectionReason.NONE:
            raise ValueError(OrderRejectionReason.RISK_NOT_APPROVED.value)
        return risk

    @classmethod
    def _validate_risk_consistency(cls, risk: RiskDecisionState, request: OrderRequest) -> None:
        expected_side = cls.side_from_direction(risk.direction)
        if expected_side is None or request.side is not expected_side:
            raise ValueError(OrderRejectionReason.INVALID_DIRECTION.value)
        if request.quantity != risk.approved_quantity:
            raise ValueError(OrderRejectionReason.QUANTITY_MISMATCH.value)
        cls.validate_order_type_fields(
            request.order_type,
            request.side,
            request.limit_price,
            request.trigger_price,
            risk.entry_price,
        )

    @staticmethod
    def side_from_direction(direction: TradeDirection) -> OrderSide | None:
        if direction is TradeDirection.BULLISH:
            return OrderSide.BUY
        if direction is TradeDirection.BEARISH:
            return OrderSide.SELL
        return None

    @staticmethod
    def _finite_real(name: str, value: Real) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be a finite real number.")
        number = float(value)
        if not isfinite(number):
            raise ValueError(f"{name} must be a finite real number.")
        return number

    @classmethod
    def _optional_positive_real(cls, name: str, value: Real | None) -> float | None:
        if value is None:
            return None
        number = cls._finite_real(name, value)
        if number <= 0:
            raise ValueError(f"{name} must be greater than zero.")
        return number

    @staticmethod
    def _positive_int(name: str, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer.")
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero.")
        return value
