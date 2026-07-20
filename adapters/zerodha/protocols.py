"""
Narrow read-only Zerodha client protocols.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol


class ZerodhaReadOnlyAuthClientProtocol(Protocol):
    def set_access_token(self, access_token: str) -> None:
        ...

    def profile(self) -> Mapping[str, object]:
        ...


class ZerodhaReadOnlyInstrumentClientProtocol(Protocol):
    def instruments(self, exchange: str) -> Sequence[Mapping[str, object]]:
        ...


class ZerodhaReadOnlyTickerClientProtocol(Protocol):
    def set_callbacks(
        self,
        *,
        on_connect,
        on_ticks,
        on_close,
        on_error,
        on_reconnect,
        on_noreconnect,
    ) -> None:
        ...

    def connect(self, *, threaded: bool = True) -> None:
        ...

    def close(self) -> None:
        ...

    def subscribe(self, instrument_tokens: list[int]) -> None:
        ...

    def set_mode(self, mode: str, instrument_tokens: list[int]) -> None:
        ...
