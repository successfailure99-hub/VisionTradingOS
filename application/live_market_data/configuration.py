"""
Live market-data runtime configuration.
"""

from dataclasses import dataclass

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription


def _api_key_hint(api_key: str) -> str:
    suffix = api_key[-4:] if len(api_key) >= 4 else api_key
    return f"****{suffix}"


@dataclass(frozen=True, slots=True, repr=False)
class LiveMarketDataConfiguration:
    api_key: str
    subscriptions: tuple[ZerodhaInstrumentSubscription, ...]
    auto_connect: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str):
            raise TypeError("api_key must be a non-empty string")
        api_key = self.api_key.strip()
        if not api_key:
            raise ValueError("api_key must be a non-empty string")
        if not isinstance(self.auto_connect, bool):
            raise TypeError("auto_connect must be bool")
        subscriptions = tuple(self.subscriptions)
        if not subscriptions:
            raise ValueError("at least one subscription is required")
        tokens = set()
        instruments = set()
        for subscription in subscriptions:
            if not isinstance(subscription, ZerodhaInstrumentSubscription):
                raise TypeError("subscriptions must contain ZerodhaInstrumentSubscription values")
            if subscription.instrument_token in tokens:
                raise ValueError("duplicate instrument token")
            if subscription.instrument in instruments:
                raise ValueError("duplicate instrument")
            tokens.add(subscription.instrument_token)
            instruments.add(subscription.instrument)
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "subscriptions", subscriptions)

    @property
    def api_key_hint(self) -> str:
        return _api_key_hint(self.api_key)

    def __repr__(self) -> str:
        return (
            "LiveMarketDataConfiguration("
            f"api_key='{self.api_key_hint}', "
            f"subscriptions={len(self.subscriptions)}, "
            f"auto_connect={self.auto_connect})"
        )

    __str__ = __repr__
