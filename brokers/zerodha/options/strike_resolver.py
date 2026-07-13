"""
Available-strike, strike-step, and ATM resolution.
"""

from datetime import date, datetime
from math import isclose

from brokers.zerodha.options.catalogue import ZerodhaOptionContractCatalogue
from brokers.zerodha.options.enums import ZerodhaOptionRight
from brokers.zerodha.options.models import require_positive_float, require_supported_underlying
from core.enums.instrument import Instrument


class ZerodhaOptionStrikeResolver:
    def __init__(self, catalogue: ZerodhaOptionContractCatalogue):
        if not isinstance(catalogue, ZerodhaOptionContractCatalogue):
            raise TypeError("catalogue must be ZerodhaOptionContractCatalogue")
        self._catalogue = catalogue

    def available_strikes(self, underlying: Instrument, *, expiry: date) -> tuple[float, ...]:
        return self._paired_strikes(underlying, expiry=_date(expiry, "expiry"))

    def infer_strike_step(self, underlying: Instrument, *, expiry: date) -> float:
        strikes = self._paired_strikes(underlying, expiry=_date(expiry, "expiry"))
        if len(strikes) < 2:
            raise ValueError("at least two paired strikes are required")
        diffs = [round(strikes[i + 1] - strikes[i], 10) for i in range(len(strikes) - 1)]
        candidate = min(diff for diff in diffs if diff > 0)
        for diff in diffs:
            multiple = diff / candidate
            if not isclose(multiple, round(multiple), rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError("irregular strike grid")
        return candidate

    def resolve_atm(self, underlying: Instrument, *, expiry: date, underlying_price: float) -> float:
        price = require_positive_float(underlying_price, "underlying_price")
        strikes = self._paired_strikes(underlying, expiry=_date(expiry, "expiry"))
        if not strikes:
            raise ValueError("no paired strikes available")
        return min(strikes, key=lambda strike: (abs(strike - price), strike))

    def strike_window(
        self,
        underlying: Instrument,
        *,
        expiry: date,
        underlying_price: float,
        strikes_each_side: int,
    ) -> tuple[float, ...]:
        if isinstance(strikes_each_side, bool) or not isinstance(strikes_each_side, int):
            raise TypeError("strikes_each_side must be int")
        if strikes_each_side < 0:
            raise ValueError("strikes_each_side must be non-negative")
        expiry = _date(expiry, "expiry")
        strikes = self._paired_strikes(underlying, expiry=expiry)
        atm = self.resolve_atm(underlying, expiry=expiry, underlying_price=underlying_price)
        index = strikes.index(atm)
        start = index - strikes_each_side
        end = index + strikes_each_side + 1
        if start < 0 or end > len(strikes):
            raise ValueError("requested symmetric strike window unavailable")
        return strikes[start:end]

    def _paired_strikes(self, underlying: Instrument, *, expiry: date) -> tuple[float, ...]:
        require_supported_underlying(underlying)
        strikes = []
        all_contracts = self._catalogue.contracts_for(underlying, expiry=expiry)
        for strike in sorted({contract.strike for contract in all_contracts}):
            calls = self._catalogue.contracts_for(underlying, expiry=expiry, strike=strike, right=ZerodhaOptionRight.CALL)
            puts = self._catalogue.contracts_for(underlying, expiry=expiry, strike=strike, right=ZerodhaOptionRight.PUT)
            if len(calls) == 1 and len(puts) == 1:
                strikes.append(strike)
        return tuple(strikes)


def _date(value: date, field_name: str) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError(f"{field_name} must be date")
    return value
