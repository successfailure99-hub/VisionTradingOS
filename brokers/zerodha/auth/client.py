"""
Injectable Zerodha authentication client boundary.
"""

from collections.abc import Mapping
from typing import Protocol


class ZerodhaAuthClientProtocol(Protocol):
    def login_url(self) -> str:
        ...

    def generate_session(
        self,
        request_token: str,
        api_secret: str,
    ) -> Mapping[str, object]:
        ...

    def set_access_token(self, access_token: str) -> None:
        ...

    def profile(self) -> Mapping[str, object]:
        ...


class KiteConnectAuthClient:
    def __init__(self, api_key: str):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        try:
            from kiteconnect import KiteConnect
        except ImportError as exc:
            raise RuntimeError(
                "kiteconnect is required to instantiate KiteConnectAuthClient"
            ) from exc
        self._client = KiteConnect(api_key=api_key.strip())

    def login_url(self) -> str:
        return self._client.login_url()

    def generate_session(
        self,
        request_token: str,
        api_secret: str,
    ) -> Mapping[str, object]:
        return self._client.generate_session(request_token, api_secret=api_secret)

    def set_access_token(self, access_token: str) -> None:
        self._client.set_access_token(access_token)

    def profile(self) -> Mapping[str, object]:
        return self._client.profile()
