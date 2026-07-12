"""
Safe Zerodha credential model.
"""

from dataclasses import dataclass


def _normalize_secret(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _api_key_hint(api_key: str) -> str:
    suffix = api_key[-4:] if len(api_key) >= 4 else api_key
    return f"****{suffix}"


@dataclass(frozen=True, slots=True, repr=False)
class ZerodhaCredentials:
    api_key: str
    api_secret: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "api_key", _normalize_secret(self.api_key, "api_key"))
        object.__setattr__(self, "api_secret", _normalize_secret(self.api_secret, "api_secret"))

    def __repr__(self) -> str:
        return f"ZerodhaCredentials(api_key='{_api_key_hint(self.api_key)}', api_secret='********')"

    __str__ = __repr__

    @property
    def api_key_hint(self) -> str:
        return _api_key_hint(self.api_key)
