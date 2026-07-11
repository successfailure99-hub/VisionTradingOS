"""
Position Management Engine V1.
"""

from datetime import datetime

from core.base_engine import BaseEngine
from core.events import POSITION_CLOSED, POSITION_OPENED, POSITION_UPDATED
from engines.position.calculator import PositionCalculator
from engines.position.enums import PositionUpdateType
from engines.position.models import PositionFill, PositionMark, PositionState


class PositionEngine(BaseEngine):
    """
    Latest-only position lifecycle manager for one symbol, exchange, and timeframe.

    Position Engine V1 consumes confirmed incremental fill deltas and explicit
    mark-price updates. It does not place orders, call brokers, fetch prices,
    select contracts, recalculate risk, persist positions, maintain balances,
    or calculate brokerage, taxes, fees, slippage, margin, or portfolio-level
    exposure. Calls are expected to be serialized and single-threaded.
    """

    def __init__(
        self,
        event_bus,
        symbol: str,
        exchange: str,
        timeframe: str,
    ):
        super().__init__(event_bus)
        self._symbol = self._normalize_symbol(symbol)
        self._exchange = self._normalize_exchange(exchange)
        self._timeframe = self._normalize_timeframe(timeframe)
        self._state: PositionState | None = None
        self._processed_execution_ids: set[str] = set()
        self._timestamp_is_aware: bool | None = None
        self._last_timestamp: datetime | None = None
        self._latest_mark: PositionMark | None = None

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def exchange(self) -> str:
        return self._exchange

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def state(self) -> PositionState | None:
        return self._state

    @property
    def latest_mark(self) -> PositionMark | None:
        return self._latest_mark

    @property
    def processed_execution_count(self) -> int:
        return len(self._processed_execution_ids)

    def apply_fill(self, fill: PositionFill) -> PositionState:
        canonical = self._canonicalize_fill(fill)
        if canonical.execution_id in self._processed_execution_ids:
            return self._state

        self._validate_timestamp(canonical.timestamp)
        state = PositionCalculator.apply_fill(self._state, canonical)
        self._state = state
        self._data = state
        self._processed_execution_ids.add(canonical.execution_id)
        self._accept_timestamp(canonical.timestamp)

        if state.last_update_type in {PositionUpdateType.OPEN, PositionUpdateType.REVERSE}:
            self._event_bus.publish(POSITION_OPENED, state)
        elif state.last_update_type is PositionUpdateType.CLOSE:
            self._event_bus.publish(POSITION_CLOSED, state)
        else:
            self._event_bus.publish(POSITION_UPDATED, state)
        return state

    def apply_mark(self, mark: PositionMark) -> PositionState:
        if self._state is None:
            raise ValueError("Cannot apply a mark before the first fill.")
        canonical = self._canonicalize_mark(mark)
        if canonical == self._latest_mark:
            return self._state

        self._validate_timestamp(canonical.timestamp)
        state = PositionCalculator.apply_mark(self._state, canonical)
        self._state = state
        self._data = state
        self._latest_mark = canonical
        self._accept_timestamp(canonical.timestamp)
        self._event_bus.publish(POSITION_UPDATED, state)
        return state

    def process_fill(self, fill: PositionFill) -> PositionState:
        return self.apply_fill(fill)

    def process_mark(self, mark: PositionMark) -> PositionState:
        return self.apply_mark(mark)

    def reset(self) -> None:
        super().clear()
        self._state = None
        self._processed_execution_ids.clear()
        self._timestamp_is_aware = None
        self._last_timestamp = None
        self._latest_mark = None

    def clear(self) -> None:
        self.reset()

    def _canonicalize_fill(self, fill: PositionFill) -> PositionFill:
        if not isinstance(fill, PositionFill):
            raise TypeError("PositionEngine expects a PositionFill object.")
        canonical = PositionFill(
            execution_id=fill.execution_id,
            client_order_id=fill.client_order_id,
            broker_order_id=fill.broker_order_id,
            symbol=fill.symbol,
            exchange=fill.exchange,
            timeframe=fill.timeframe,
            timestamp=fill.timestamp,
            side=fill.side,
            quantity=fill.quantity,
            price=fill.price,
        )
        self._validate_context(canonical.symbol, canonical.exchange, canonical.timeframe)
        return canonical

    def _canonicalize_mark(self, mark: PositionMark) -> PositionMark:
        if not isinstance(mark, PositionMark):
            raise TypeError("PositionEngine expects a PositionMark object.")
        canonical = PositionMark(
            symbol=mark.symbol,
            exchange=mark.exchange,
            timeframe=mark.timeframe,
            timestamp=mark.timestamp,
            mark_price=mark.mark_price,
        )
        self._validate_context(canonical.symbol, canonical.exchange, canonical.timeframe)
        return canonical

    def _validate_context(self, symbol: str, exchange: str, timeframe: str) -> None:
        if symbol != self._symbol:
            raise ValueError("Position context symbol does not match engine context.")
        if exchange != self._exchange:
            raise ValueError("Position context exchange does not match engine context.")
        if timeframe != self._timeframe:
            raise ValueError("Position context timeframe does not match engine context.")

    def _validate_timestamp(self, timestamp: datetime) -> None:
        if not isinstance(timestamp, datetime):
            raise ValueError("timestamp must be a datetime.")
        timestamp_is_aware = timestamp.tzinfo is not None
        if self._timestamp_is_aware is not None and timestamp_is_aware != self._timestamp_is_aware:
            raise ValueError("Position timestamp timezone-awareness mode changed.")
        if self._last_timestamp is not None and timestamp < self._last_timestamp:
            raise ValueError("Stale Position update received.")

    def _accept_timestamp(self, timestamp: datetime) -> None:
        if self._timestamp_is_aware is None:
            self._timestamp_is_aware = timestamp.tzinfo is not None
        self._last_timestamp = timestamp

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        if not isinstance(symbol, str):
            raise ValueError("PositionEngine symbol must be a string.")
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("PositionEngine symbol cannot be empty.")
        return normalized

    @staticmethod
    def _normalize_exchange(exchange: str) -> str:
        if not isinstance(exchange, str):
            raise ValueError("PositionEngine exchange must be a string.")
        normalized = exchange.strip().upper()
        if not normalized:
            raise ValueError("PositionEngine exchange cannot be empty.")
        return normalized

    @staticmethod
    def _normalize_timeframe(timeframe: str) -> str:
        if not isinstance(timeframe, str):
            raise ValueError("PositionEngine timeframe must be a string.")
        normalized = timeframe.strip()
        if not normalized:
            raise ValueError("PositionEngine timeframe cannot be empty.")
        return normalized
