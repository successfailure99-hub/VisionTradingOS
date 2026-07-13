"""
Option subscription transport adapter.
"""

from typing import Protocol

from brokers.zerodha.market_data import ZerodhaSubscriptionMode, ZerodhaTickerClientProtocol
from brokers.zerodha.market_data.client import KiteTickerClient


class ZerodhaOptionSubscriptionTransportProtocol(Protocol):
    def subscribe(self, instrument_tokens: list[int]) -> None:
        ...

    def unsubscribe(self, instrument_tokens: list[int]) -> None:
        ...

    def set_mode(self, mode: str, instrument_tokens: list[int]) -> None:
        ...


class ZerodhaTickerOptionSubscriptionTransport:
    def __init__(self, client: ZerodhaTickerClientProtocol):
        for name in ("subscribe", "unsubscribe", "set_mode"):
            if not hasattr(client, name):
                raise TypeError("client must implement ticker subscription methods")
        self._client = client

    def subscribe(self, instrument_tokens: list[int]) -> None:
        self._client.subscribe(_validate_tokens(instrument_tokens))

    def unsubscribe(self, instrument_tokens: list[int]) -> None:
        self._client.unsubscribe(_validate_tokens(instrument_tokens))

    def set_mode(self, mode: str, instrument_tokens: list[int]) -> None:
        if not isinstance(mode, str) or not mode:
            raise ValueError("mode must be non-empty string")
        self._client.set_mode(mode, _validate_tokens(instrument_tokens))


def to_kite_mode(mode: ZerodhaSubscriptionMode) -> str:
    if mode is ZerodhaSubscriptionMode.LTP:
        return KiteTickerClient.MODE_LTP
    if mode is ZerodhaSubscriptionMode.QUOTE:
        return KiteTickerClient.MODE_QUOTE
    if mode is ZerodhaSubscriptionMode.FULL:
        return KiteTickerClient.MODE_FULL
    raise TypeError("mode must be ZerodhaSubscriptionMode")


def _validate_tokens(tokens: list[int]) -> list[int]:
    if not isinstance(tokens, list):
        raise TypeError("instrument_tokens must be list")
    if not tokens:
        raise ValueError("instrument_tokens must not be empty")
    seen = set()
    for token in tokens:
        if isinstance(token, bool) or not isinstance(token, int) or token <= 0:
            raise ValueError("instrument_tokens must contain positive integers")
        if token in seen:
            raise ValueError("instrument_tokens must be unique")
        seen.add(token)
    return list(tokens)
