"""
Option Chain Engine V1.
"""

from datetime import date, datetime
from math import isfinite
from numbers import Real

from core.base_engine import BaseEngine
from core.events import OPTION_CHAIN_READY, OPTION_CHAIN_UPDATED
from engines.option_chain.calculator import OptionChainCalculator
from engines.option_chain.enums import OptionType
from engines.option_chain.models import (
    OptionChainSnapshot,
    OptionChainState,
    OptionLeg,
    OptionStrike,
)


class OptionChainEngine(BaseEngine):
    """
    Deterministic option-chain analysis engine for one symbol and expiry.

    One instance handles one externally managed symbol, exchange, and
    expiry context. Inputs are complete option-chain snapshots. V1 is
    broker-independent: it does not fetch data, authenticate, scrape,
    persist history, or place trades.

    ATM uses the nearest available strike. OI-derived support and
    resistance are positioning references. Max Pain is calculated from
    open-interest payout minimization. Pressure classification is based
    on aggregate signed change in OI, and positioning bias is
    descriptive, not a trade signal.

    Calls are assumed serialized and single-threaded. Persistence and
    historical analysis are outside V1.
    """

    def __init__(
        self,
        event_bus,
        symbol: str,
        exchange: str,
        expiry_date: date,
    ):
        super().__init__(event_bus)

        self._symbol = self._normalize_text("symbol", symbol)
        self._exchange = self._normalize_text("exchange", exchange)
        self._expiry_date = self._validate_expiry_date(expiry_date)
        self._snapshot: OptionChainSnapshot | None = None
        self._state: OptionChainState | None = None
        self._timestamp_is_aware: bool | None = None

    @property
    def snapshot(self) -> OptionChainSnapshot | None:
        return self._snapshot

    @property
    def state(self) -> OptionChainState | None:
        return self._state

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def exchange(self) -> str:
        return self._exchange

    @property
    def expiry_date(self) -> date:
        return self._expiry_date

    def update(
        self,
        snapshot: OptionChainSnapshot,
    ) -> OptionChainState:
        canonical = self._canonicalize_snapshot(snapshot)

        if self._snapshot is not None:
            if canonical.timestamp < self._snapshot.timestamp:
                raise ValueError(
                    "Stale OptionChainSnapshot received: "
                    f"{canonical.timestamp.isoformat()} < "
                    f"{self._snapshot.timestamp.isoformat()}"
                )

            if canonical == self._snapshot:
                return self._state

        was_ready = self._state is not None
        state = OptionChainCalculator.calculate(canonical)

        self._snapshot = canonical
        self._state = state
        self._data = state

        self._event_bus.publish(OPTION_CHAIN_UPDATED, state)
        if not was_ready:
            self._event_bus.publish(OPTION_CHAIN_READY, state)

        return state

    def process(
        self,
        snapshot: OptionChainSnapshot,
    ) -> OptionChainState:
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

    def _canonicalize_snapshot(
        self,
        snapshot: OptionChainSnapshot,
    ) -> OptionChainSnapshot:
        if not isinstance(snapshot, OptionChainSnapshot):
            raise TypeError("OptionChainEngine expects an OptionChainSnapshot object.")

        symbol = self._normalize_text("snapshot symbol", snapshot.symbol)
        exchange = self._normalize_text("snapshot exchange", snapshot.exchange)

        if symbol != self._symbol:
            raise ValueError("OptionChainSnapshot symbol does not match engine context.")

        if exchange != self._exchange:
            raise ValueError("OptionChainSnapshot exchange does not match engine context.")

        if (
            not isinstance(snapshot.expiry_date, date)
            or isinstance(snapshot.expiry_date, datetime)
        ):
            raise ValueError("OptionChainSnapshot expiry_date must be a date.")

        if snapshot.expiry_date != self._expiry_date:
            raise ValueError("OptionChainSnapshot expiry_date does not match engine context.")

        if not isinstance(snapshot.timestamp, datetime):
            raise ValueError("OptionChainSnapshot timestamp must be a datetime.")

        timestamp_is_aware = snapshot.timestamp.tzinfo is not None
        if self._timestamp_is_aware is not None and timestamp_is_aware != self._timestamp_is_aware:
            raise ValueError("OptionChainSnapshot timestamp timezone-awareness mode changed.")

        underlying_price = self._validate_positive_real(
            "OptionChainSnapshot underlying_price",
            snapshot.underlying_price,
        )

        if not isinstance(snapshot.strikes, tuple):
            raise ValueError("OptionChainSnapshot strikes must be a tuple.")

        if not snapshot.strikes:
            raise ValueError("OptionChainSnapshot strikes cannot be empty.")

        validated_strikes = tuple(self._validate_strikes(snapshot.strikes))
        canonical_strikes = tuple(sorted(validated_strikes, key=lambda strike: strike.strike_price))

        canonical = OptionChainSnapshot(
            symbol=symbol,
            exchange=exchange,
            expiry_date=snapshot.expiry_date,
            timestamp=snapshot.timestamp,
            underlying_price=underlying_price,
            strikes=canonical_strikes,
        )

        if self._timestamp_is_aware is None:
            self._timestamp_is_aware = timestamp_is_aware

        return canonical

    def _validate_strikes(
        self,
        strikes: tuple[OptionStrike, ...],
    ) -> tuple[OptionStrike, ...]:
        seen = set()
        validated = []

        for strike in strikes:
            if not isinstance(strike, OptionStrike):
                raise ValueError("OptionChainSnapshot strikes must contain OptionStrike objects.")

            strike_price = self._validate_positive_real("OptionStrike strike_price", strike.strike_price)
            if strike_price in seen:
                raise ValueError("OptionChainSnapshot strike prices must be unique.")
            seen.add(strike_price)

            if strike.call is None and strike.put is None:
                raise ValueError("OptionStrike must contain at least one option leg.")

            call = self._validate_leg("call", strike.call, OptionType.CALL)
            put = self._validate_leg("put", strike.put, OptionType.PUT)

            validated.append(
                OptionStrike(
                    strike_price=strike_price,
                    call=call,
                    put=put,
                )
            )

        return tuple(validated)

    def _validate_leg(
        self,
        name: str,
        leg: OptionLeg | None,
        expected_type: OptionType,
    ) -> OptionLeg | None:
        if leg is None:
            return None

        if not isinstance(leg, OptionLeg):
            raise ValueError(f"OptionStrike {name} must be an OptionLeg.")

        if leg.option_type is not expected_type:
            raise ValueError(f"OptionStrike {name} leg has the wrong option type.")

        last_price = self._validate_non_negative_real("OptionLeg last_price", leg.last_price)
        open_interest = self._validate_non_negative_int("OptionLeg open_interest", leg.open_interest)
        change_in_open_interest = self._validate_int(
            "OptionLeg change_in_open_interest",
            leg.change_in_open_interest,
        )
        volume = self._validate_non_negative_int("OptionLeg volume", leg.volume)
        bid_price = self._validate_optional_non_negative_real("OptionLeg bid_price", leg.bid_price)
        ask_price = self._validate_optional_non_negative_real("OptionLeg ask_price", leg.ask_price)

        if (
            bid_price is not None
            and ask_price is not None
            and bid_price > 0
            and ask_price > 0
            and bid_price > ask_price
        ):
            raise ValueError("OptionLeg bid_price cannot be greater than ask_price.")

        return OptionLeg(
            option_type=leg.option_type,
            last_price=last_price,
            open_interest=open_interest,
            change_in_open_interest=change_in_open_interest,
            volume=volume,
            bid_price=bid_price,
            ask_price=ask_price,
        )

    def _validate_expiry_date(self, value: date) -> date:
        if not isinstance(value, date) or isinstance(value, datetime):
            raise ValueError("OptionChainEngine expiry_date must be a date.")

        return value

    def _normalize_text(self, name: str, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"OptionChainEngine {name} must be a string.")

        normalized = value.strip().upper()
        if not normalized:
            raise ValueError(f"OptionChainEngine {name} cannot be empty.")

        return normalized

    def _validate_positive_real(self, name: str, value: Real) -> float:
        number = self._validate_real(name, value)
        if number <= 0:
            raise ValueError(f"{name} must be greater than zero.")
        return number

    def _validate_non_negative_real(self, name: str, value: Real) -> float:
        number = self._validate_real(name, value)
        if number < 0:
            raise ValueError(f"{name} must be greater than or equal to zero.")
        return number

    def _validate_optional_non_negative_real(
        self,
        name: str,
        value: Real | None,
    ) -> float | None:
        if value is None:
            return None
        return self._validate_non_negative_real(name, value)

    def _validate_real(self, name: str, value: Real) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be a finite real number.")

        number = float(value)
        if not isfinite(number):
            raise ValueError(f"{name} must be a finite real number.")

        return number

    def _validate_int(self, name: str, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer.")

        return value

    def _validate_non_negative_int(self, name: str, value: int) -> int:
        integer = self._validate_int(name, value)
        if integer < 0:
            raise ValueError(f"{name} must be greater than or equal to zero.")

        return integer