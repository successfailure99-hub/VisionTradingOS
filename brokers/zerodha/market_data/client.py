"""
Official KiteTicker client boundary.
"""

from threading import RLock
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


def _ticker_socket_available(ticker) -> bool:
    if not hasattr(ticker, "ws"):
        return True
    return getattr(ticker, "ws") is not None


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
        self._lock = RLock()
        self._desired_subscription_tokens: set[int] = set()
        self._desired_modes_by_token: dict[int, str] = {}
        self._connection_generation = 0
        self._last_connection_object = None
        self._applied_subscription_tokens: set[int] = set()
        self._applied_modes_by_token: dict[int, str] = {}
        self._handling_connect_callback = False
        self._post_connect_recovery_callbacks: list[object] = []
        self._recovery_callback_failure_count = 0
        self._last_recovery_callback_error: str | None = None

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
        self._ticker.on_connect = self._on_connect_wrapper(on_connect)
        self._ticker.on_ticks = on_ticks
        self._ticker.on_close = on_close
        self._ticker.on_error = on_error
        self._ticker.on_reconnect = on_reconnect
        self._ticker.on_noreconnect = on_noreconnect

    def register_reconnect_recovery(self, callback) -> None:
        if not callable(callback):
            raise TypeError("reconnect recovery callback must be callable")
        with self._lock:
            if any(existing is callback for existing in self._post_connect_recovery_callbacks):
                return
            self._post_connect_recovery_callbacks.append(callback)

    def connect(self, *, threaded: bool = True) -> None:
        self._ticker.connect(threaded=threaded)

    def close(self) -> None:
        self._ticker.close()

    def subscribe(self, instrument_tokens: list[int]) -> None:
        tokens = _validate_tokens(instrument_tokens)
        self._ticker.subscribe(tokens)
        with self._lock:
            self._desired_subscription_tokens.update(tokens)
            if self._handling_connect_callback:
                self._applied_subscription_tokens.update(tokens)

    def unsubscribe(self, instrument_tokens: list[int]) -> None:
        tokens = _validate_tokens(instrument_tokens)
        if _ticker_socket_available(self._ticker):
            self._ticker.unsubscribe(tokens)
        with self._lock:
            for token in tokens:
                self._desired_subscription_tokens.discard(token)
                self._desired_modes_by_token.pop(token, None)
                self._applied_subscription_tokens.discard(token)
                self._applied_modes_by_token.pop(token, None)

    def set_mode(self, mode: str, instrument_tokens: list[int]) -> None:
        if not isinstance(mode, str) or not mode:
            raise ValueError("mode must be non-empty string")
        tokens = _validate_tokens(instrument_tokens)
        self._ticker.set_mode(mode, tokens)
        with self._lock:
            for token in tokens:
                self._desired_modes_by_token[token] = mode
                if self._handling_connect_callback:
                    self._applied_modes_by_token[token] = mode

    def _on_connect_wrapper(self, callback):
        def wrapped(ws, response):
            connection_object = getattr(self._ticker, "ws", None)
            with self._lock:
                duplicate = connection_object is not None and connection_object is self._last_connection_object
                if not duplicate:
                    self._last_connection_object = connection_object
                    self._connection_generation += 1
                    self._applied_subscription_tokens.clear()
                    self._applied_modes_by_token.clear()
                    self._handling_connect_callback = True
            if duplicate:
                if callback is not None:
                    callback(ws, response)
                return
            try:
                if callback is not None:
                    callback(ws, response)
                self._run_post_connect_recovery_callbacks()
                self._recover_desired_subscriptions()
            finally:
                with self._lock:
                    self._handling_connect_callback = False
        return wrapped

    def _run_post_connect_recovery_callbacks(self) -> None:
        with self._lock:
            callbacks = tuple(self._post_connect_recovery_callbacks)
        for callback in callbacks:
            try:
                callback()
            except Exception as exc:
                with self._lock:
                    self._recovery_callback_failure_count += 1
                    self._last_recovery_callback_error = f"{exc.__class__.__name__}: reconnect recovery callback failed"

    def _recover_desired_subscriptions(self) -> None:
        with self._lock:
            missing_tokens = sorted(self._desired_subscription_tokens - self._applied_subscription_tokens)
            desired_modes = dict(self._desired_modes_by_token)
            applied_modes = dict(self._applied_modes_by_token)
        if missing_tokens:
            self._ticker.subscribe(missing_tokens)
            with self._lock:
                self._applied_subscription_tokens.update(missing_tokens)
        mode_groups: dict[str, list[int]] = {}
        for token, mode in sorted(desired_modes.items()):
            if token not in self._desired_subscription_tokens:
                continue
            if applied_modes.get(token) == mode:
                continue
            mode_groups.setdefault(mode, []).append(token)
        for mode, tokens in mode_groups.items():
            self._ticker.set_mode(mode, tokens)
            with self._lock:
                for token in tokens:
                    self._applied_modes_by_token[token] = mode


def _validate_tokens(instrument_tokens: list[int]) -> list[int]:
    if not isinstance(instrument_tokens, list):
        raise TypeError("instrument_tokens must be list")
    if not instrument_tokens:
        raise ValueError("instrument_tokens must not be empty")
    seen: set[int] = set()
    for token in instrument_tokens:
        if isinstance(token, bool) or not isinstance(token, int) or token <= 0:
            raise ValueError("instrument_tokens must contain positive integers")
        if token in seen:
            raise ValueError("instrument_tokens must be unique")
        seen.add(token)
    return list(instrument_tokens)
