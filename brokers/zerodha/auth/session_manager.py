"""
Zerodha authentication session manager.
"""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from threading import RLock

from brokers.zerodha.auth.client import KiteConnectAuthClient, ZerodhaAuthClientProtocol
from brokers.zerodha.auth.credentials import ZerodhaCredentials
from brokers.zerodha.auth.enums import ZerodhaAuthStatus
from brokers.zerodha.auth.models import ZerodhaAuthSnapshot, ZerodhaLoginRequest, ZerodhaSession


Clock = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(UTC)


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


class ZerodhaSessionManager:
    def __init__(
        self,
        credentials: ZerodhaCredentials,
        *,
        client: ZerodhaAuthClientProtocol | None = None,
        clock: Clock | None = None,
    ):
        if not isinstance(credentials, ZerodhaCredentials):
            raise TypeError("credentials must be ZerodhaCredentials")
        self._credentials = credentials
        self._client = client or KiteConnectAuthClient(credentials.api_key)
        self._clock = clock or _default_clock
        self._lock = RLock()
        self._status = ZerodhaAuthStatus.CREATED
        self._session: ZerodhaSession | None = None
        self._login_url: str | None = None
        self._last_error: str | None = None

    @property
    def status(self) -> ZerodhaAuthStatus:
        with self._lock:
            return self._status

    @property
    def session(self) -> ZerodhaSession | None:
        with self._lock:
            return self._session

    def create_login_request(self) -> ZerodhaLoginRequest:
        with self._lock:
            login_url = _require_text(self._client.login_url(), "login_url")
            self._login_url = login_url
            self._status = ZerodhaAuthStatus.LOGIN_URL_READY
            self._last_error = None
            return ZerodhaLoginRequest(login_url=login_url, created_at=self._now())

    def authenticate(
        self,
        request_token: str,
        *,
        expires_at: datetime | None = None,
    ) -> ZerodhaAuthSnapshot:
        token = _require_text(request_token, "request_token")
        with self._lock:
            self._status = ZerodhaAuthStatus.AUTHENTICATING
            access_token: str | None = None
            try:
                response = self._client.generate_session(token, self._credentials.api_secret)
                access_token = _require_text(
                    str(response.get("access_token", "")),
                    "access_token",
                )
                self._client.set_access_token(access_token)
                profile = self._client.profile()
                user_id = self._resolve_user_id(response, profile)
                self._session = ZerodhaSession(
                    user_id=user_id,
                    access_token=access_token,
                    authenticated_at=self._now(),
                    expires_at=expires_at,
                )
                self._status = ZerodhaAuthStatus.AUTHENTICATED
                self._last_error = None
                return self.snapshot()
            except Exception as exc:
                self._session = None
                self._status = ZerodhaAuthStatus.ERROR
                self._last_error = self._safe_error(exc, token, access_token)
                raise

    def restore_session(
        self,
        *,
        user_id: str,
        access_token: str,
        authenticated_at: datetime,
        expires_at: datetime | None = None,
        validate_profile: bool = True,
    ) -> ZerodhaAuthSnapshot:
        normalized_user_id = _require_text(user_id, "user_id")
        normalized_access_token = _require_text(access_token, "access_token")
        _require_aware(authenticated_at, "authenticated_at")
        if expires_at is not None:
            _require_aware(expires_at, "expires_at")
        with self._lock:
            try:
                self._client.set_access_token(normalized_access_token)
                if validate_profile:
                    profile_user_id = self._profile_user_id(self._client.profile())
                    if profile_user_id != normalized_user_id:
                        raise ValueError("profile user_id does not match restored session")
                self._session = ZerodhaSession(
                    user_id=normalized_user_id,
                    access_token=normalized_access_token,
                    authenticated_at=authenticated_at,
                    expires_at=expires_at,
                )
                self._status = ZerodhaAuthStatus.AUTHENTICATED
                self._last_error = None
                return self.snapshot()
            except Exception as exc:
                self._session = None
                self._status = ZerodhaAuthStatus.ERROR
                self._last_error = self._safe_error(exc, access_token=normalized_access_token)
                raise

    def validate_session(self) -> ZerodhaAuthSnapshot:
        with self._lock:
            if self._session is None:
                raise RuntimeError("no active Zerodha session")
            if self._session.is_expired(self._now()):
                self._session = None
                self._status = ZerodhaAuthStatus.EXPIRED
                return self.snapshot()
            try:
                profile_user_id = self._profile_user_id(self._client.profile())
                if profile_user_id != self._session.user_id:
                    raise ValueError("profile user_id does not match active session")
                self._status = ZerodhaAuthStatus.AUTHENTICATED
                self._last_error = None
                return self.snapshot()
            except Exception as exc:
                active_token = self._session.access_token
                self._session = None
                self._status = ZerodhaAuthStatus.ERROR
                self._last_error = self._safe_error(exc, access_token=active_token)
                raise

    def logout(self) -> ZerodhaAuthSnapshot:
        with self._lock:
            self._session = None
            self._login_url = None
            self._status = ZerodhaAuthStatus.LOGGED_OUT
            self._last_error = None
            return self.snapshot()

    def snapshot(self) -> ZerodhaAuthSnapshot:
        with self._lock:
            session = self._session
            return ZerodhaAuthSnapshot(
                status=self._status,
                user_id=session.user_id if session else None,
                api_key_hint=self._credentials.api_key_hint,
                authenticated_at=session.authenticated_at if session else None,
                expires_at=session.expires_at if session else None,
                last_error=self._last_error,
                login_url=self._login_url,
            )

    def is_authenticated(self) -> bool:
        with self._lock:
            return self._status is ZerodhaAuthStatus.AUTHENTICATED and self._session is not None

    def _now(self) -> datetime:
        return _require_aware(self._clock(), "clock result")

    def _resolve_user_id(self, response: Mapping[str, object], profile: Mapping[str, object]) -> str:
        profile_user_id = self._profile_user_id(profile, required=False)
        if profile_user_id:
            return profile_user_id
        return _require_text(str(response.get("user_id", "")), "user_id")

    def _profile_user_id(self, profile: Mapping[str, object], *, required: bool = True) -> str:
        raw_user_id = profile.get("user_id")
        if raw_user_id is None and not required:
            return ""
        return _require_text(str(raw_user_id or ""), "profile user_id")

    def _safe_error(
        self,
        exc: Exception,
        request_token: str | None = None,
        access_token: str | None = None,
    ) -> str:
        message = str(exc) or exc.__class__.__name__
        secrets = [
            self._credentials.api_key,
            self._credentials.api_secret,
            request_token,
            access_token,
            self._session.access_token if self._session else None,
        ]
        for secret in secrets:
            if secret:
                message = message.replace(secret, "[REDACTED]")
        return message
