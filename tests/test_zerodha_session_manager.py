"""
Tests for the Zerodha authentication session manager.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from threading import RLock

import pytest

from brokers.zerodha.auth import (
    ZerodhaAuthStatus,
    ZerodhaCredentials,
    ZerodhaSession,
    ZerodhaSessionManager,
)


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


class FakeAuthClient:
    def __init__(self):
        self.login_calls = 0
        self.generate_calls = []
        self.applied_tokens = []
        self.profile_calls = 0
        self.profile_user_id = "AB1234"
        self.fail_generate = None
        self.fail_profile = None
        self.access_token = "access_token_123"

    def login_url(self):
        self.login_calls += 1
        return "https://kite.zerodha.com/connect/login?api_key=abcd"

    def generate_session(self, request_token, api_secret):
        self.generate_calls.append((request_token, api_secret))
        if self.fail_generate:
            raise self.fail_generate
        return {"access_token": self.access_token, "user_id": "AB1234"}

    def set_access_token(self, access_token):
        self.applied_tokens.append(access_token)

    def profile(self):
        self.profile_calls += 1
        if self.fail_profile:
            raise self.fail_profile
        return {"user_id": self.profile_user_id}


def clock():
    return NOW


def manager(client=None):
    return ZerodhaSessionManager(
        ZerodhaCredentials("api_key_1234", "api_secret_5678"),
        client=client or FakeAuthClient(),
        clock=clock,
    )


def authenticate(subject, request_token="request_token_abc"):
    return subject.authenticate(request_token, expires_at=NOW + timedelta(hours=6))


def test_initial_status_is_created():
    subject = manager()

    assert subject.status is ZerodhaAuthStatus.CREATED
    assert subject.session is None


def test_login_request_transitions_to_login_url_ready_and_returns_safe_request():
    client = FakeAuthClient()
    subject = manager(client)

    request = subject.create_login_request()

    assert subject.status is ZerodhaAuthStatus.LOGIN_URL_READY
    assert request.login_url.startswith("https://kite.zerodha.com")
    assert request.created_at == NOW
    assert client.login_calls == 1
    assert "api_secret" not in request.login_url


def test_request_token_is_not_retained_after_authentication():
    subject = manager()

    snapshot = authenticate(subject)

    assert snapshot.status is ZerodhaAuthStatus.AUTHENTICATED
    assert "request_token_abc" not in repr(snapshot)
    assert "request_token_abc" not in vars(subject).values()


def test_successful_authentication_transitions_and_applies_token_and_validates_profile():
    client = FakeAuthClient()
    subject = manager(client)

    snapshot = authenticate(subject)

    assert subject.status is ZerodhaAuthStatus.AUTHENTICATED
    assert snapshot.user_id == "AB1234"
    assert client.generate_calls == [("request_token_abc", "api_secret_5678")]
    assert client.applied_tokens == ["access_token_123"]
    assert client.profile_calls == 1


def test_snapshot_does_not_contain_access_token_or_api_secret():
    subject = manager()

    snapshot = authenticate(subject)

    assert "access_token_123" not in repr(snapshot)
    assert "api_secret_5678" not in repr(snapshot)
    assert snapshot.api_key_hint == "****1234"


def test_session_representation_redacts_token():
    session = ZerodhaSession(
        user_id="AB1234",
        access_token="access_token_123",
        authenticated_at=NOW,
        expires_at=None,
    )

    assert "access_token_123" not in repr(session)
    assert "[REDACTED]" in repr(session)


def test_authentication_error_transitions_to_error_and_redacts_api_key_secret_and_request_token():
    client = FakeAuthClient()
    client.fail_generate = RuntimeError(
        "failed api_key_1234 api_secret_5678 request_token_abc"
    )
    subject = manager(client)

    with pytest.raises(RuntimeError):
        subject.authenticate("request_token_abc")

    snapshot = subject.snapshot()
    assert snapshot.status is ZerodhaAuthStatus.ERROR
    assert subject.session is None
    assert "api_key_1234" not in snapshot.last_error
    assert "api_secret_5678" not in snapshot.last_error
    assert "request_token_abc" not in snapshot.last_error


def test_authentication_error_redacts_generated_access_token():
    client = FakeAuthClient()
    client.fail_profile = RuntimeError("bad access_token_123")
    subject = manager(client)

    with pytest.raises(RuntimeError):
        subject.authenticate("request_token_abc")

    assert "access_token_123" not in subject.snapshot().last_error


def test_empty_request_token_rejected():
    subject = manager()

    with pytest.raises(ValueError):
        subject.authenticate(" ")


def test_restore_session_succeeds_and_validates_user_id():
    client = FakeAuthClient()
    subject = manager(client)

    snapshot = subject.restore_session(
        user_id="AB1234",
        access_token="restored_token",
        authenticated_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )

    assert snapshot.status is ZerodhaAuthStatus.AUTHENTICATED
    assert client.applied_tokens == ["restored_token"]
    assert client.profile_calls == 1


def test_restore_session_mismatch_fails_safely():
    client = FakeAuthClient()
    client.profile_user_id = "OTHER"
    subject = manager(client)

    with pytest.raises(ValueError):
        subject.restore_session(
            user_id="AB1234",
            access_token="restored_token",
            authenticated_at=NOW,
        )

    assert subject.status is ZerodhaAuthStatus.ERROR
    assert subject.session is None


def test_explicit_expired_session_transitions_to_expired():
    subject = manager()
    subject.restore_session(
        user_id="AB1234",
        access_token="restored_token",
        authenticated_at=NOW - timedelta(hours=2),
        expires_at=NOW - timedelta(hours=1),
        validate_profile=False,
    )

    snapshot = subject.validate_session()

    assert snapshot.status is ZerodhaAuthStatus.EXPIRED
    assert subject.session is None


def test_active_session_validates_successfully():
    client = FakeAuthClient()
    subject = manager(client)
    authenticate(subject)

    snapshot = subject.validate_session()

    assert snapshot.status is ZerodhaAuthStatus.AUTHENTICATED
    assert subject.is_authenticated() is True
    assert client.profile_calls == 2


def test_profile_validation_failure_clears_session():
    client = FakeAuthClient()
    subject = manager(client)
    authenticate(subject)
    client.fail_profile = RuntimeError("profile failure")

    with pytest.raises(RuntimeError):
        subject.validate_session()

    assert subject.status is ZerodhaAuthStatus.ERROR
    assert subject.session is None


def test_logout_clears_session_and_is_idempotent():
    subject = manager()
    authenticate(subject)

    first = subject.logout()
    second = subject.logout()

    assert first.status is ZerodhaAuthStatus.LOGGED_OUT
    assert second.status is ZerodhaAuthStatus.LOGGED_OUT
    assert subject.session is None
    assert first.login_url is None


def test_repeated_login_requests_do_not_recreate_client():
    client = FakeAuthClient()
    subject = manager(client)

    subject.create_login_request()
    subject.create_login_request()

    assert client.login_calls == 2
    assert subject._client is client


def test_manager_uses_rlock():
    subject = manager()

    assert isinstance(subject._lock, type(RLock()))


def test_session_snapshots_are_immutable():
    subject = manager()
    snapshot = authenticate(subject)

    with pytest.raises(FrozenInstanceError):
        snapshot.user_id = "OTHER"


def test_time_values_are_timezone_aware():
    subject = manager()
    snapshot = authenticate(subject)

    assert snapshot.authenticated_at.tzinfo is not None
    assert snapshot.authenticated_at.utcoffset() is not None
    assert snapshot.expires_at.tzinfo is not None
    assert snapshot.expires_at.utcoffset() is not None


def test_no_credentials_are_persisted_or_files_read(monkeypatch):
    import builtins

    def forbidden_open(*args, **kwargs):
        raise AssertionError("files must not be read or written")

    monkeypatch.setattr(builtins, "open", forbidden_open)
    subject = manager()

    authenticate(subject)
    subject.validate_session()
    subject.logout()
