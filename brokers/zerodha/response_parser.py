"""
Zerodha response parsing and command translation.
"""

from datetime import datetime
from math import isfinite
from numbers import Real

from brokers.zerodha.enums import ZerodhaOrderStatus
from brokers.zerodha.models import ZerodhaOrderUpdate
from engines.order_management.enums import OrderCommandType, OrderStatus
from engines.order_management.models import OrderCommand, OrderState


class ZerodhaResponseParser:
    ACKNOWLEDGEMENT_STATUSES = {
        ZerodhaOrderStatus.PUT_ORDER_REQ_RECEIVED,
        ZerodhaOrderStatus.VALIDATION_PENDING,
        ZerodhaOrderStatus.OPEN_PENDING,
        ZerodhaOrderStatus.OPEN,
        ZerodhaOrderStatus.TRIGGER_PENDING,
    }
    MODIFICATION_STATUSES = {
        ZerodhaOrderStatus.MODIFY_VALIDATION_PENDING,
        ZerodhaOrderStatus.MODIFY_PENDING,
        ZerodhaOrderStatus.MODIFIED,
    }

    @staticmethod
    def parse_order_update(payload: dict) -> ZerodhaOrderUpdate:
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict.")
        order_id = ZerodhaResponseParser._non_empty_string(payload.get("order_id"), "order_id")
        status = ZerodhaResponseParser._status(payload.get("status"))
        timestamp = ZerodhaResponseParser._timestamp(
            payload.get("order_timestamp", payload.get("exchange_update_timestamp"))
        )
        filled_quantity = ZerodhaResponseParser._non_negative_int(payload.get("filled_quantity"), "filled_quantity")
        pending_quantity = ZerodhaResponseParser._non_negative_int(payload.get("pending_quantity"), "pending_quantity")
        average_price = ZerodhaResponseParser._non_negative_real(payload.get("average_price"), "average_price")
        status_message = payload.get("status_message")
        if status_message is not None:
            if not isinstance(status_message, str):
                raise ValueError("status_message must be a string.")
            status_message = status_message.strip() or None
        return ZerodhaOrderUpdate(
            order_id=order_id,
            status=status,
            timestamp=timestamp,
            filled_quantity=filled_quantity,
            pending_quantity=pending_quantity,
            average_price=average_price,
            status_message=status_message,
        )

    @staticmethod
    def to_order_command(previous: OrderState, update: ZerodhaOrderUpdate) -> OrderCommand | None:
        if not isinstance(previous, OrderState):
            raise TypeError("previous must be an OrderState.")
        if not isinstance(update, ZerodhaOrderUpdate):
            raise TypeError("update must be a ZerodhaOrderUpdate.")
        if update.filled_quantity > previous.quantity:
            raise ValueError("Broker filled quantity exceeds internal order quantity.")
        if update.filled_quantity < previous.filled_quantity:
            raise ValueError("Broker cumulative filled quantity moved backwards.")

        if update.status in ZerodhaResponseParser.ACKNOWLEDGEMENT_STATUSES:
            if previous.status is OrderStatus.PENDING_SUBMISSION:
                return OrderCommand(
                    command_type=OrderCommandType.ACKNOWLEDGE,
                    client_order_id=previous.client_order_id,
                    timestamp=update.timestamp,
                    broker_order_id=update.order_id,
                )
            return ZerodhaResponseParser._fill_command(previous, update)

        if update.status in ZerodhaResponseParser.MODIFICATION_STATUSES:
            return None

        if update.status is ZerodhaOrderStatus.COMPLETE:
            if update.filled_quantity != previous.quantity:
                raise ValueError("Complete broker update must equal internal order quantity.")
            return ZerodhaResponseParser._fill_command(previous, update)

        fill = ZerodhaResponseParser._fill_command(previous, update)
        if fill is not None:
            return fill

        if update.status is ZerodhaOrderStatus.CANCELLED:
            if previous.status is OrderStatus.CANCELLED:
                return None
            return OrderCommand(
                command_type=OrderCommandType.CANCEL,
                client_order_id=previous.client_order_id,
                timestamp=update.timestamp,
                broker_order_id=update.order_id,
            )

        if update.status is ZerodhaOrderStatus.REJECTED:
            if previous.status is OrderStatus.REJECTED:
                return None
            return OrderCommand(
                command_type=OrderCommandType.REJECT,
                client_order_id=previous.client_order_id,
                timestamp=update.timestamp,
                broker_order_id=update.order_id,
                rejection_message=update.status_message or "Broker rejected order",
            )

        return None

    @staticmethod
    def _fill_command(previous: OrderState, update: ZerodhaOrderUpdate) -> OrderCommand | None:
        delta = update.filled_quantity - previous.filled_quantity
        if delta < 0:
            raise ValueError("Broker cumulative filled quantity moved backwards.")
        if delta == 0:
            return None
        return OrderCommand(
            command_type=OrderCommandType.FILL,
            client_order_id=previous.client_order_id,
            timestamp=update.timestamp,
            broker_order_id=update.order_id,
            fill_quantity=delta,
            fill_price=update.average_price,
        )

    @staticmethod
    def _status(value: object) -> ZerodhaOrderStatus:
        if not isinstance(value, str):
            raise ValueError("status must be a string.")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("status cannot be empty.")
        try:
            return ZerodhaOrderStatus(normalized)
        except ValueError:
            return ZerodhaOrderStatus.UNKNOWN

    @staticmethod
    def _timestamp(value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                try:
                    return datetime.fromisoformat(cleaned)
                except ValueError as exc:
                    raise ValueError("Invalid broker timestamp.") from exc
        raise ValueError("Broker timestamp is required.")

    @staticmethod
    def _non_empty_string(value: object, name: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string.")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{name} cannot be empty.")
        return normalized

    @staticmethod
    def _non_negative_int(value: object, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer.")
        if value < 0:
            raise ValueError(f"{name} cannot be negative.")
        return value

    @staticmethod
    def _non_negative_real(value: object, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be a finite real number.")
        number = float(value)
        if not isfinite(number) or number < 0:
            raise ValueError(f"{name} must be a finite non-negative number.")
        return number
