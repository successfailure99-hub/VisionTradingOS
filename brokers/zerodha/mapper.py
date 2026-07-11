"""
Kite request mapping for Zerodha Broker Adapter V1.
"""

from collections import OrderedDict

from brokers.zerodha.enums import BrokerAction
from brokers.zerodha.models import BrokerRequest
from engines.order_management.enums import OrderCommandType, OrderSide, OrderStatus, OrderType
from engines.order_management.models import OrderCommand, OrderState


class ZerodhaOrderMapper:
    """
    Converts immutable internal order state into deterministic Kite payloads.
    """

    SIDE_MAP = {
        OrderSide.BUY: "BUY",
        OrderSide.SELL: "SELL",
    }
    ORDER_TYPE_MAP = {
        OrderType.MARKET: "MARKET",
        OrderType.LIMIT: "LIMIT",
        OrderType.STOP_MARKET: "SL-M",
        OrderType.STOP_LIMIT: "SL",
    }

    @staticmethod
    def place_request(order: OrderState) -> BrokerRequest:
        if not isinstance(order, OrderState):
            raise TypeError("order must be an OrderState.")
        if order.status is not OrderStatus.PENDING_SUBMISSION:
            raise ValueError("Only pending-submission orders can be placed.")
        if order.broker_order_id is not None:
            raise ValueError("Pending order must not already have a broker order ID.")
        if order.quantity <= 0:
            raise ValueError("order quantity must be positive.")

        payload = OrderedDict(
            [
                ("variety", "regular"),
                ("tradingsymbol", order.symbol),
                ("exchange", order.exchange),
                ("transaction_type", ZerodhaOrderMapper._map_side(order.side)),
                ("order_type", ZerodhaOrderMapper._map_order_type(order.order_type)),
                ("quantity", order.quantity),
                ("product", "MIS"),
                ("validity", "DAY"),
                ("tag", ZerodhaOrderMapper.normalize_tag(order.client_order_id)),
            ]
        )
        ZerodhaOrderMapper._add_price_fields(payload, order.order_type, order.limit_price, order.trigger_price)
        return BrokerRequest(
            action=BrokerAction.PLACE,
            client_order_id=order.client_order_id,
            broker_order_id=None,
            parameters=tuple(payload.items()),
        )

    @staticmethod
    def modify_request(order: OrderState, command: OrderCommand) -> BrokerRequest:
        if not isinstance(order, OrderState):
            raise TypeError("order must be an OrderState.")
        if not isinstance(command, OrderCommand):
            raise TypeError("command must be an OrderCommand.")
        if command.command_type is not OrderCommandType.MODIFY:
            raise ValueError("modify_request requires a MODIFY command.")
        if not order.broker_order_id:
            raise ValueError("broker_order_id is required.")
        if order.status not in {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}:
            raise ValueError("Only submitted or partially-filled orders can be modified.")

        quantity = command.new_quantity if command.new_quantity is not None else order.quantity
        limit_price = command.new_limit_price if command.new_limit_price is not None else order.limit_price
        trigger_price = command.new_trigger_price if command.new_trigger_price is not None else order.trigger_price
        payload = OrderedDict(
            [
                ("variety", "regular"),
                ("order_id", order.broker_order_id),
                ("order_type", ZerodhaOrderMapper._map_order_type(order.order_type)),
                ("quantity", quantity),
                ("validity", "DAY"),
            ]
        )
        ZerodhaOrderMapper._add_price_fields(payload, order.order_type, limit_price, trigger_price)
        return BrokerRequest(
            action=BrokerAction.MODIFY,
            client_order_id=order.client_order_id,
            broker_order_id=order.broker_order_id,
            parameters=tuple(payload.items()),
        )

    @staticmethod
    def cancel_request(order: OrderState) -> BrokerRequest:
        if not isinstance(order, OrderState):
            raise TypeError("order must be an OrderState.")
        if not order.broker_order_id:
            raise ValueError("broker_order_id is required.")
        if order.status not in {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}:
            raise ValueError("Only submitted or partially-filled orders can be cancelled.")
        payload = OrderedDict(
            [
                ("variety", "regular"),
                ("order_id", order.broker_order_id),
            ]
        )
        return BrokerRequest(
            action=BrokerAction.CANCEL,
            client_order_id=order.client_order_id,
            broker_order_id=order.broker_order_id,
            parameters=tuple(payload.items()),
        )

    @staticmethod
    def normalize_tag(client_order_id: str) -> str:
        if not isinstance(client_order_id, str):
            raise ValueError("client_order_id must be a string.")
        tag = "".join(character for character in client_order_id if character.isalnum())[:20]
        if not tag:
            raise ValueError("client_order_id does not contain a valid Kite tag.")
        return tag

    @staticmethod
    def _add_price_fields(payload: OrderedDict, order_type: OrderType, limit_price: float | None, trigger_price: float | None) -> None:
        if order_type is OrderType.LIMIT:
            payload["price"] = limit_price
            return
        if order_type is OrderType.STOP_MARKET:
            payload["trigger_price"] = trigger_price
            return
        if order_type is OrderType.STOP_LIMIT:
            payload["price"] = limit_price
            payload["trigger_price"] = trigger_price

    @staticmethod
    def _map_side(side: OrderSide) -> str:
        try:
            return ZerodhaOrderMapper.SIDE_MAP[side]
        except KeyError as exc:
            raise ValueError("Unsupported order side.") from exc

    @staticmethod
    def _map_order_type(order_type: OrderType) -> str:
        try:
            return ZerodhaOrderMapper.ORDER_TYPE_MAP[order_type]
        except KeyError as exc:
            raise ValueError("Unsupported order type.") from exc
