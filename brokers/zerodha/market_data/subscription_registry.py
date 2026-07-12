"""
In-memory Zerodha subscription registry.
"""

from threading import RLock

from core.enums.instrument import Instrument

from brokers.zerodha.market_data.models import ZerodhaInstrumentSubscription


class ZerodhaSubscriptionRegistry:
    def __init__(
        self,
        subscriptions: tuple[ZerodhaInstrumentSubscription, ...] = (),
    ):
        self._lock = RLock()
        self._subscriptions: dict[int, ZerodhaInstrumentSubscription] = {}
        for subscription in subscriptions:
            self._add_unlocked(subscription)

    def add(
        self,
        subscription: ZerodhaInstrumentSubscription,
    ) -> tuple[ZerodhaInstrumentSubscription, ...]:
        with self._lock:
            self._add_unlocked(subscription)
            return self.all()

    def remove_by_token(
        self,
        instrument_token: int,
    ) -> tuple[ZerodhaInstrumentSubscription, ...]:
        with self._lock:
            if instrument_token not in self._subscriptions:
                raise ValueError("Unknown instrument token")
            del self._subscriptions[instrument_token]
            return self.all()

    def get_by_token(
        self,
        instrument_token: int,
    ) -> ZerodhaInstrumentSubscription | None:
        with self._lock:
            return self._subscriptions.get(instrument_token)

    def get_by_instrument(
        self,
        instrument: Instrument,
    ) -> ZerodhaInstrumentSubscription | None:
        with self._lock:
            for subscription in self._subscriptions.values():
                if subscription.instrument is instrument:
                    return subscription
            return None

    def all(
        self,
    ) -> tuple[ZerodhaInstrumentSubscription, ...]:
        with self._lock:
            return tuple(self._subscriptions.values())

    def tokens(
        self,
    ) -> tuple[int, ...]:
        with self._lock:
            return tuple(self._subscriptions.keys())

    def clear(self) -> tuple[ZerodhaInstrumentSubscription, ...]:
        with self._lock:
            self._subscriptions.clear()
            return self.all()

    def replace(
        self,
        subscriptions: tuple[ZerodhaInstrumentSubscription, ...],
    ) -> tuple[ZerodhaInstrumentSubscription, ...]:
        replacement = ZerodhaSubscriptionRegistry(subscriptions)
        with self._lock:
            self._subscriptions = dict(replacement._subscriptions)
            return self.all()

    def _add_unlocked(self, subscription: ZerodhaInstrumentSubscription) -> None:
        if not isinstance(subscription, ZerodhaInstrumentSubscription):
            raise TypeError("subscription must be ZerodhaInstrumentSubscription")
        if subscription.instrument_token in self._subscriptions:
            raise ValueError("Duplicate instrument token")
        if any(existing.instrument is subscription.instrument for existing in self._subscriptions.values()):
            raise ValueError("Duplicate instrument")
        self._subscriptions[subscription.instrument_token] = subscription
