"""
Official Zerodha instrument API client boundary.
"""

from collections.abc import Mapping, Sequence
from typing import Protocol


class ZerodhaInstrumentClientProtocol(Protocol):
    def instruments(
        self,
        exchange: str | None = None,
    ) -> Sequence[Mapping[str, object]]:
        ...


class KiteInstrumentClient:
    def __init__(
        self,
        *,
        api_key: str,
        access_token: str,
    ):
        self._api_key = _require_text(api_key, "api_key")
        normalized_access_token = _require_text(access_token, "access_token")
        self._redactions = (self._api_key, normalized_access_token)
        try:
            from kiteconnect import KiteConnect
        except Exception as exc:
            raise RuntimeError("kiteconnect is required for Zerodha instrument discovery") from exc
        self._client = KiteConnect(api_key=self._api_key)
        self._client.set_access_token(normalized_access_token)

    def instruments(
        self,
        exchange: str | None = None,
    ) -> Sequence[Mapping[str, object]]:
        try:
            if exchange is None:
                return self._client.instruments()
            return self._client.instruments(exchange)
        except Exception as exc:
            raise RuntimeError(self._safe_error(exc)) from exc

    def __repr__(self) -> str:
        return "KiteInstrumentClient(api_key='[REDACTED]', access_token='[REDACTED]')"

    __str__ = __repr__

    def _safe_error(self, exc: Exception) -> str:
        message = f"{exc.__class__.__name__}: {exc}"
        for secret in self._redactions:
            message = message.replace(secret, "[REDACTED]")
        return message


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized
