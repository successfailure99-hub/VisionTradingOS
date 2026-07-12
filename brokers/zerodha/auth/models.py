"""
Immutable public Zerodha authentication models.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from brokers.zerodha.auth.enums import ZerodhaAuthStatus


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _require_aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class ZerodhaLoginRequest:
    login_url: str
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "login_url", _require_text(self.login_url, "login_url"))
        object.__setattr__(self, "created_at", _require_aware(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True, repr=False)
class ZerodhaSession:
    user_id: str
    access_token: str
    authenticated_at: datetime
    expires_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_id", _require_text(self.user_id, "user_id"))
        object.__setattr__(self, "access_token", _require_text(self.access_token, "access_token"))
        object.__setattr__(
            self,
            "authenticated_at",
            _require_aware(self.authenticated_at, "authenticated_at"),
        )
        if self.expires_at is not None:
            object.__setattr__(self, "expires_at", _require_aware(self.expires_at, "expires_at"))
            if self.expires_at <= self.authenticated_at:
                raise ValueError("expires_at must be later than authenticated_at")

    def __repr__(self) -> str:
        return (
            "ZerodhaSession("
            f"user_id='{self.user_id}', "
            "access_token='[REDACTED]', "
            f"authenticated_at={self.authenticated_at!r}, "
            f"expires_at={self.expires_at!r})"
        )

    __str__ = __repr__

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        checked_at = now or datetime.now(UTC)
        _require_aware(checked_at, "now")
        return checked_at >= self.expires_at


@dataclass(frozen=True, slots=True)
class ZerodhaAuthSnapshot:
    status: ZerodhaAuthStatus
    user_id: str | None
    api_key_hint: str
    authenticated_at: datetime | None
    expires_at: datetime | None
    last_error: str | None
    login_url: str | None
