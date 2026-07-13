"""
In-memory immutable option-contract catalogue.
"""

from datetime import date, datetime
from threading import RLock

from brokers.zerodha.options.enums import ZerodhaOptionRight
from brokers.zerodha.options.models import ZerodhaOptionContract, require_supported_underlying
from core.enums.instrument import Instrument


class ZerodhaOptionContractCatalogue:
    def __init__(self, contracts: tuple[ZerodhaOptionContract, ...] = ()):
        self._lock = RLock()
        self._contracts: tuple[ZerodhaOptionContract, ...] = ()
        self._by_token: dict[int, ZerodhaOptionContract] = {}
        if contracts:
            self.replace(contracts)

    def replace(self, contracts: tuple[ZerodhaOptionContract, ...]) -> tuple[ZerodhaOptionContract, ...]:
        prepared = self._prepare(tuple(contracts))
        with self._lock:
            self._contracts = prepared
            self._by_token = {contract.instrument_token: contract for contract in prepared}
            return self._contracts

    def all(self) -> tuple[ZerodhaOptionContract, ...]:
        with self._lock:
            return self._contracts

    def clear(self) -> tuple[ZerodhaOptionContract, ...]:
        with self._lock:
            previous = self._contracts
            self._contracts = ()
            self._by_token = {}
            return previous

    def by_token(self, instrument_token: int) -> ZerodhaOptionContract | None:
        if isinstance(instrument_token, bool) or not isinstance(instrument_token, int):
            raise TypeError("instrument_token must be int")
        with self._lock:
            return self._by_token.get(instrument_token)

    def expiries(self, underlying: Instrument, *, as_of: date) -> tuple[date, ...]:
        require_supported_underlying(underlying)
        as_of = self._date(as_of, "as_of")
        with self._lock:
            dates = {contract.expiry for contract in self._contracts if contract.underlying is underlying and contract.expiry >= as_of}
            return tuple(sorted(dates))

    def contracts_for(
        self,
        underlying: Instrument,
        *,
        expiry: date | None = None,
        strike: float | None = None,
        right: ZerodhaOptionRight | None = None,
    ) -> tuple[ZerodhaOptionContract, ...]:
        require_supported_underlying(underlying)
        if expiry is not None:
            expiry = self._date(expiry, "expiry")
        if right is not None and not isinstance(right, ZerodhaOptionRight):
            raise TypeError("right must be ZerodhaOptionRight")
        with self._lock:
            contracts = []
            for contract in self._contracts:
                if contract.underlying is not underlying:
                    continue
                if expiry is not None and contract.expiry != expiry:
                    continue
                if strike is not None and contract.strike != float(strike):
                    continue
                if right is not None and contract.right is not right:
                    continue
                contracts.append(contract)
            return tuple(contracts)

    def _prepare(self, contracts: tuple[ZerodhaOptionContract, ...]) -> tuple[ZerodhaOptionContract, ...]:
        tokens: set[int] = set()
        identities = set()
        for contract in contracts:
            if not isinstance(contract, ZerodhaOptionContract):
                raise TypeError("contracts must contain ZerodhaOptionContract values")
            if contract.instrument_token in tokens:
                raise ValueError("duplicate instrument token")
            identity = (contract.underlying, contract.venue, contract.expiry, contract.strike, contract.right)
            if identity in identities:
                raise ValueError("duplicate option contract identity")
            tokens.add(contract.instrument_token)
            identities.add(identity)
        return contracts

    def _date(self, value: date, field_name: str) -> date:
        if isinstance(value, datetime) or not isinstance(value, date):
            raise TypeError(f"{field_name} must be date")
        return value
