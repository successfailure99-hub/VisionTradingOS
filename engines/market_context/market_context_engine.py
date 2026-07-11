"""
Market Context Engine V1.
"""

from datetime import datetime
from math import isfinite
from numbers import Real

from core.base_engine import BaseEngine
from core.enums.instrument import Instrument
from core.events import MARKET_CONTEXT_UPDATED
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context.calculator import MarketContextCalculator
from engines.market_context.models import MarketContextSnapshot, MarketContextState
from engines.option_chain.models import OptionChainState
from engines.price_action.models import PriceActionState
from engines.vwap.levels import VWAPLevels


class MarketContextEngine(BaseEngine):
    """
    Deterministic context engine for one symbol and timeframe.

    Price Action and Option Chain are primary; VWAP, CPR, and Camarilla
    are secondary. Inputs are complete context snapshots supplied by
    upstream orchestration. The engine describes context and conflict,
    does not produce trades, and assumes serialized single-threaded
    calls. Historical persistence and AI interpretation are outside V1.
    """

    def __init__(self, event_bus, symbol: str, timeframe: str):
        super().__init__(event_bus)
        self._symbol = self._normalize_symbol(symbol)
        self._timeframe = self._normalize_timeframe(timeframe)
        self._snapshot: MarketContextSnapshot | None = None
        self._state: MarketContextState | None = None
        self._timestamp_is_aware: bool | None = None

    @property
    def snapshot(self) -> MarketContextSnapshot | None:
        return self._snapshot

    @property
    def state(self) -> MarketContextState | None:
        return self._state

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    def update(self, snapshot: MarketContextSnapshot) -> MarketContextState:
        canonical = self._canonicalize_snapshot(snapshot)

        if self._snapshot is not None:
            if canonical.timestamp < self._snapshot.timestamp:
                raise ValueError(
                    "Stale MarketContextSnapshot received: "
                    f"{canonical.timestamp.isoformat()} < {self._snapshot.timestamp.isoformat()}"
                )
            if canonical == self._snapshot:
                return self._state

        state = MarketContextCalculator.calculate(canonical)
        self._snapshot = canonical
        self._state = state
        self._data = state
        self._event_bus.publish(MARKET_CONTEXT_UPDATED, state)
        return state

    def process(self, snapshot: MarketContextSnapshot) -> MarketContextState:
        """
        Alias for update().
        """

        return self.update(snapshot)

    def reset(self) -> None:
        super().clear()
        self._snapshot = None
        self._state = None
        self._timestamp_is_aware = None

    def clear(self) -> None:
        self.reset()

    def _canonicalize_snapshot(self, snapshot: MarketContextSnapshot) -> MarketContextSnapshot:
        if not isinstance(snapshot, MarketContextSnapshot):
            raise TypeError("MarketContextEngine expects a MarketContextSnapshot object.")

        symbol = self._normalize_symbol(snapshot.symbol)
        timeframe = self._normalize_timeframe(snapshot.timeframe)
        if symbol != self._symbol:
            raise ValueError("MarketContextSnapshot symbol does not match engine context.")
        if timeframe != self._timeframe:
            raise ValueError("MarketContextSnapshot timeframe does not match engine context.")
        if not isinstance(snapshot.timestamp, datetime):
            raise ValueError("MarketContextSnapshot timestamp must be a datetime.")

        timestamp_is_aware = snapshot.timestamp.tzinfo is not None
        if self._timestamp_is_aware is not None and timestamp_is_aware != self._timestamp_is_aware:
            raise ValueError("MarketContextSnapshot timestamp timezone-awareness mode changed.")

        current_price = self._validate_positive_real("current_price", snapshot.current_price)
        session_high = self._validate_positive_real("session_high", snapshot.session_high)
        session_low = self._validate_positive_real("session_low", snapshot.session_low)
        if session_high < session_low:
            raise ValueError("MarketContextSnapshot session_high must be greater than or equal to session_low.")
        if not session_low <= current_price <= session_high:
            raise ValueError("MarketContextSnapshot current_price must be inside session range.")

        self._validate_price_action(snapshot.price_action, snapshot.timestamp)
        self._validate_option_chain(snapshot.option_chain, snapshot.timestamp)
        self._validate_vwap(snapshot.vwap, snapshot.timestamp)
        self._validate_cpr(snapshot.cpr, snapshot.timestamp)
        self._validate_camarilla(snapshot.camarilla, snapshot.timestamp)

        canonical = MarketContextSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=snapshot.timestamp,
            current_price=current_price,
            session_high=session_high,
            session_low=session_low,
            price_action=snapshot.price_action,
            option_chain=snapshot.option_chain,
            vwap=snapshot.vwap,
            cpr=snapshot.cpr,
            camarilla=snapshot.camarilla,
        )
        if self._timestamp_is_aware is None:
            self._timestamp_is_aware = timestamp_is_aware
        return canonical

    def _validate_price_action(self, state: PriceActionState | None, timestamp: datetime) -> None:
        if state is None:
            return
        if not isinstance(state, PriceActionState):
            raise ValueError("price_action must be a PriceActionState.")
        if self._normalize_symbol(state.symbol) != self._symbol:
            raise ValueError("Price Action symbol does not match engine context.")
        if self._normalize_timeframe(state.timeframe) != self._timeframe:
            raise ValueError("Price Action timeframe does not match engine context.")
        if state.last_candle.end_time > timestamp:
            raise ValueError("Price Action state cannot be newer than context timestamp.")
        self._validate_positive_real("Price Action close", state.last_candle.close)

    def _validate_option_chain(self, state: OptionChainState | None, timestamp: datetime) -> None:
        if state is None:
            return
        if not isinstance(state, OptionChainState):
            raise ValueError("option_chain must be an OptionChainState.")
        if self._normalize_symbol(state.symbol) != self._symbol:
            raise ValueError("Option Chain symbol does not match engine context.")
        if state.timestamp > timestamp:
            raise ValueError("Option Chain state cannot be newer than context timestamp.")
        self._validate_positive_real("Option Chain underlying_price", state.underlying_price)

    def _validate_vwap(self, state: VWAPLevels | None, timestamp: datetime) -> None:
        if state is None:
            return
        if not isinstance(state, VWAPLevels):
            raise ValueError("vwap must be a VWAPLevels object.")
        if state.timestamp > timestamp:
            raise ValueError("VWAP state cannot be newer than context timestamp.")
        if state.trading_date != timestamp.date():
            raise ValueError("VWAP trading date must match context date.")
        if state.symbol != self._instrument_for_symbol():
            raise ValueError("VWAP instrument does not match engine context.")
        self._validate_positive_real("VWAP", state.vwap)

    def _validate_cpr(self, state: CPRLevels | None, timestamp: datetime) -> None:
        if state is None:
            return
        if not isinstance(state, CPRLevels):
            raise ValueError("cpr must be a CPRLevels object.")
        if state.trading_date != timestamp.date():
            raise ValueError("CPR trading date must match context date.")
        values = (
            state.previous_high,
            state.previous_low,
            state.previous_close,
            state.pivot,
            state.bc,
            state.tc,
            state.width,
            state.width_percentage,
        )
        for value in values:
            self._validate_positive_real("CPR level", value)
        if state.bc > state.tc:
            raise ValueError("CPR bc must be less than or equal to tc.")

    def _validate_camarilla(self, state: CamarillaLevels | None, timestamp: datetime) -> None:
        if state is None:
            return
        if not isinstance(state, CamarillaLevels):
            raise ValueError("camarilla must be a CamarillaLevels object.")
        if state.trading_date != timestamp.date():
            raise ValueError("Camarilla trading date must match context date.")
        values = (
            state.previous_high,
            state.previous_low,
            state.previous_close,
            state.pivot,
            state.h3,
            state.h4,
            state.h5,
            state.h6,
            state.l3,
            state.l4,
            state.l5,
            state.l6,
        )
        for value in values:
            self._validate_positive_real("Camarilla level", value)
        if not (state.h6 > state.h5 > state.h4 > state.h3 > state.l3 > state.l4 > state.l5 > state.l6):
            raise ValueError("Camarilla levels are not strictly ordered.")

    def _instrument_for_symbol(self) -> Instrument:
        return Instrument.from_symbol(self._symbol)

    def _normalize_symbol(self, symbol: str) -> str:
        if not isinstance(symbol, str):
            raise ValueError("MarketContextEngine symbol must be a string.")
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("MarketContextEngine symbol cannot be empty.")
        return normalized

    def _normalize_timeframe(self, timeframe: str) -> str:
        if not isinstance(timeframe, str):
            raise ValueError("MarketContextEngine timeframe must be a string.")
        normalized = timeframe.strip()
        if not normalized:
            raise ValueError("MarketContextEngine timeframe cannot be empty.")
        return normalized

    def _validate_positive_real(self, name: str, value: Real) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be a finite real number.")
        number = float(value)
        if not isfinite(number):
            raise ValueError(f"{name} must be a finite real number.")
        if number <= 0:
            raise ValueError(f"{name} must be greater than zero.")
        return number