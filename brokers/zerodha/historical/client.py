"""
Official Zerodha historical data client boundary.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol


class ZerodhaHistoricalClientProtocol(Protocol):
    def historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
    ) -> Sequence[Mapping[str, object]]:
        ...


class KiteHistoricalClient:
    def __init__(
        self,
        *,
        api_key: str,
        access_token: str,
    ):
        self._api_key = _text(api_key, "api_key")
        token = _text(access_token, "access_token")
        self._redactions = (self._api_key, token)
        try:
            from kiteconnect import KiteConnect
        except Exception as exc:
            raise RuntimeError("kiteconnect is required for Zerodha historical data") from exc
        self._client = KiteConnect(api_key=self._api_key)
        self._client.set_access_token(token)

    def historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
    ) -> Sequence[Mapping[str, object]]:
        try:
            return self._client.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=interval,
                continuous=continuous,
                oi=oi,
            )
        except Exception as exc:
            raise RuntimeError(self._safe_error(exc)) from exc

    def __repr__(self) -> str:
        return "KiteHistoricalClient(api_key='[REDACTED]', access_token='[REDACTED]')"

    __str__ = __repr__

    def _safe_error(self, exc: Exception) -> str:
        message = f"{exc.__class__.__name__}: {exc}"
        for secret in self._redactions:
            message = message.replace(secret, "[REDACTED]")
        return message


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized
