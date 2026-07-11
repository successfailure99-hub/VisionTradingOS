"""
Zerodha Broker Adapter V1.
"""

from brokers.base import BrokerOrderClient
from brokers.zerodha.enums import BrokerAction, BrokerExecutionMode, BrokerResultStatus
from brokers.zerodha.mapper import ZerodhaOrderMapper
from brokers.zerodha.models import BrokerExecutionResult, BrokerRequest
from engines.order_management.models import OrderCommand, OrderState


class ZerodhaBrokerAdapter:
    """
    Broker adapter for translating Vision orders into Kite requests.

    V1 is intentionally dependency-injected and safe by default. It stores
    no credentials, reads no tokens, performs no login, imports no Kite
    SDK, opens no WebSocket, and defaults to DRY_RUN so tests and local
    development cannot place real orders by accident.
    """

    def __init__(
        self,
        client: BrokerOrderClient | None = None,
        mode: BrokerExecutionMode = BrokerExecutionMode.DRY_RUN,
    ):
        if not isinstance(mode, BrokerExecutionMode):
            raise ValueError("mode must be a BrokerExecutionMode.")
        if mode is BrokerExecutionMode.CLIENT and client is None:
            raise ValueError("CLIENT mode requires a broker client.")
        self._client = client
        self._mode = mode

    @property
    def mode(self) -> BrokerExecutionMode:
        return self._mode

    def place(self, order: OrderState) -> BrokerExecutionResult:
        request = ZerodhaOrderMapper.place_request(order)
        return self._execute(request)

    def modify(self, order: OrderState, command: OrderCommand) -> BrokerExecutionResult:
        request = ZerodhaOrderMapper.modify_request(order, command)
        return self._execute(request)

    def cancel(self, order: OrderState) -> BrokerExecutionResult:
        request = ZerodhaOrderMapper.cancel_request(order)
        return self._execute(request)

    def _execute(self, request: BrokerRequest) -> BrokerExecutionResult:
        if self._mode is BrokerExecutionMode.DRY_RUN:
            return BrokerExecutionResult(
                action=request.action,
                status=BrokerResultStatus.DRY_RUN,
                client_order_id=request.client_order_id,
                broker_order_id=None,
                request=request,
                error_message=None,
            )

        try:
            broker_order_id = self._call_client(request)
        except Exception as exc:
            return self._failed(request, str(exc) or exc.__class__.__name__)

        if not isinstance(broker_order_id, str) or not broker_order_id.strip():
            return self._failed(request, "Broker returned an empty order ID.")
        broker_order_id = broker_order_id.strip()
        if request.action in {BrokerAction.MODIFY, BrokerAction.CANCEL} and broker_order_id != request.broker_order_id:
            return self._failed(request, "Broker returned an order ID that does not match the existing order.")
        return BrokerExecutionResult(
            action=request.action,
            status=BrokerResultStatus.ACCEPTED,
            client_order_id=request.client_order_id,
            broker_order_id=broker_order_id,
            request=request,
            error_message=None,
        )

    def _call_client(self, request: BrokerRequest) -> str:
        if self._client is None:
            raise ValueError("Broker client is required.")
        payload = request.as_dict()
        if request.action is BrokerAction.PLACE:
            return self._client.place_order(**payload)
        if request.action is BrokerAction.MODIFY:
            return self._client.modify_order(**payload)
        if request.action is BrokerAction.CANCEL:
            return self._client.cancel_order(**payload)
        raise ValueError("Unsupported broker action.")

    @staticmethod
    def _failed(request: BrokerRequest, message: str) -> BrokerExecutionResult:
        return BrokerExecutionResult(
            action=request.action,
            status=BrokerResultStatus.FAILED,
            client_order_id=request.client_order_id,
            broker_order_id=None,
            request=request,
            error_message=message,
        )
