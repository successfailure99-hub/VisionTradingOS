"""
Token-keyed option subscription registry.
"""

from threading import RLock

from brokers.zerodha.option_market_data.models import ZerodhaOptionSubscriptionEntry
from brokers.zerodha.options import ZerodhaOptionRight


class ZerodhaOptionSubscriptionRegistry:
    def __init__(self, entries: tuple[ZerodhaOptionSubscriptionEntry, ...] = ()):
        self._lock = RLock()
        self._entries: tuple[ZerodhaOptionSubscriptionEntry, ...] = ()
        self._by_token: dict[int, ZerodhaOptionSubscriptionEntry] = {}
        if entries:
            self.replace(tuple(entries))

    def replace(self, entries: tuple[ZerodhaOptionSubscriptionEntry, ...]) -> tuple[ZerodhaOptionSubscriptionEntry, ...]:
        prepared = self._prepare(tuple(entries))
        with self._lock:
            self._entries = prepared
            self._by_token = {entry.subscription.instrument_token: entry for entry in prepared}
            return self._entries

    def all(self) -> tuple[ZerodhaOptionSubscriptionEntry, ...]:
        with self._lock:
            return self._entries

    def tokens(self) -> tuple[int, ...]:
        with self._lock:
            return tuple(entry.subscription.instrument_token for entry in self._entries)

    def get_by_token(self, instrument_token: int) -> ZerodhaOptionSubscriptionEntry | None:
        if isinstance(instrument_token, bool) or not isinstance(instrument_token, int):
            raise TypeError("instrument_token must be int")
        with self._lock:
            return self._by_token.get(instrument_token)

    def contracts_for_strike(self, strike: float) -> tuple[ZerodhaOptionSubscriptionEntry, ...]:
        with self._lock:
            return tuple(entry for entry in self._entries if entry.contract.strike == float(strike))

    def entries_for_right(self, right: ZerodhaOptionRight) -> tuple[ZerodhaOptionSubscriptionEntry, ...]:
        if not isinstance(right, ZerodhaOptionRight):
            raise TypeError("right must be ZerodhaOptionRight")
        with self._lock:
            return tuple(entry for entry in self._entries if entry.contract.right is right)

    def clear(self) -> tuple[ZerodhaOptionSubscriptionEntry, ...]:
        with self._lock:
            previous = self._entries
            self._entries = ()
            self._by_token = {}
            return previous

    def _prepare(self, entries: tuple[ZerodhaOptionSubscriptionEntry, ...]) -> tuple[ZerodhaOptionSubscriptionEntry, ...]:
        tokens = set()
        identities = set()
        underlying = None
        expiry = None
        for entry in entries:
            if not isinstance(entry, ZerodhaOptionSubscriptionEntry):
                raise TypeError("entries must contain ZerodhaOptionSubscriptionEntry values")
            token = entry.subscription.instrument_token
            identity = (entry.contract.underlying, entry.contract.expiry, entry.contract.strike, entry.contract.right)
            if token in tokens:
                raise ValueError("duplicate instrument token")
            if identity in identities:
                raise ValueError("duplicate option contract identity")
            if underlying is None:
                underlying = entry.contract.underlying
                expiry = entry.contract.expiry
            elif entry.contract.underlying is not underlying or entry.contract.expiry != expiry:
                raise ValueError("registry entries must share one underlying and expiry")
            tokens.add(token)
            identities.add(identity)
        return entries
