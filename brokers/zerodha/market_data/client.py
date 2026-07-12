"""
Official KiteTicker client boundary.
"""

from typing import Protocol


class ZerodhaTickerClientProtocol(Protocol):
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

    def unsubscribe(self, instrument_tokens: list[int]) -> None:
        ...

    def set_mode(self, mode: str, instrument_tokens: list[int]) -> None:
        ...


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


class KiteTickerClient:
    MODE_LTP = "ltp"
    MODE_QUOTE = "quote"
    MODE_FULL = "full"

    def __init__(
        self,
        *,
        api_key: str,
        access_token: str,
        reconnect: bool = True,
        reconnect_max_tries: int = 50,
        reconnect_max_delay: int = 60,
    ):
        normalized_api_key = _require_text(api_key, "api_key")
        normalized_access_token = _require_text(access_token, "access_token")
        if not isinstance(reconnect, bool):
            raise TypeError("reconnect must be bool")
        for name, value in (
            ("reconnect_max_tries", reconnect_max_tries),
            ("reconnect_max_delay", reconnect_max_delay),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        try:
            from kiteconnect import KiteTicker
        except ImportError as exc:
            raise RuntimeError("kiteconnect is required to instantiate KiteTickerClient") from exc
        self._ticker = KiteTicker(
            api_key=normalized_api_key,
            access_token=normalized_access_token,
            reconnect=reconnect,
            reconnect_max_tries=reconnect_max_tries,
            reconnect_max_delay=reconnect_max_delay,
        )

    def __repr__(self) -> str:
        return "KiteTickerClient(ticker='[PRIVATE]')"

    __str__ = __repr__

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
        self._ticker.on_connect = on_connect
        self._ticker.on_ticks = on_ticks
        self._ticker.on_close = on_close
        self._ticker.on_error = on_error
        self._ticker.on_reconnect = on_reconnect
        self._ticker.on_noreconnect = on_noreconnect

    def connect(self, *, threaded: bool = True) -> None:
        self._ticker.connect(threaded=threaded)

    def close(self) -> None:
        self._ticker.close()

    def subscribe(self, instrument_tokens: list[int]) -> None:
        self._ticker.subscribe(instrument_tokens)

    def unsubscribe(self, instrument_tokens: list[int]) -> None:
        self._ticker.unsubscribe(instrument_tokens)

    def set_mode(self, mode: str, instrument_tokens: list[int]) -> None:
        self._ticker.set_mode(mode, instrument_tokens)
