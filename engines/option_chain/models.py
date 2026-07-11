"""
Immutable Option Chain Engine V1 input and output models.
"""

from dataclasses import dataclass
from datetime import date, datetime

from engines.option_chain.enums import OptionType, PositioningBias, PressureType


@dataclass(frozen=True, slots=True)
class OptionLeg:
    option_type: OptionType
    last_price: float
    open_interest: int
    change_in_open_interest: int
    volume: int
    bid_price: float | None = None
    ask_price: float | None = None


@dataclass(frozen=True, slots=True)
class OptionStrike:
    strike_price: float
    call: OptionLeg | None
    put: OptionLeg | None


@dataclass(frozen=True, slots=True)
class OptionChainSnapshot:
    symbol: str
    exchange: str
    expiry_date: date
    timestamp: datetime
    underlying_price: float
    strikes: tuple[OptionStrike, ...]

    def __post_init__(self) -> None:
        if isinstance(self.symbol, str):
            object.__setattr__(self, "symbol", self.symbol.strip().upper())

        if isinstance(self.exchange, str):
            object.__setattr__(self, "exchange", self.exchange.strip().upper())


@dataclass(frozen=True, slots=True)
class StrikeMetric:
    strike_price: float
    value: int


@dataclass(frozen=True, slots=True)
class OptionChainState:
    symbol: str
    exchange: str
    expiry_date: date
    timestamp: datetime
    underlying_price: float
    atm_strike: float

    strike_count: int

    total_call_oi: int
    total_put_oi: int
    total_call_change_oi: int
    total_put_change_oi: int

    oi_pcr: float | None
    change_oi_pcr: float | None

    max_call_oi: StrikeMetric | None
    max_put_oi: StrikeMetric | None
    max_call_change_oi: StrikeMetric | None
    max_put_change_oi: StrikeMetric | None

    resistance_strike: float | None
    support_strike: float | None
    max_pain_strike: float | None

    call_pressure: PressureType
    put_pressure: PressureType
    positioning_bias: PositioningBias

    strikes: tuple[OptionStrike, ...]