from datetime import UTC, datetime, timedelta
import json

from application.broker_session_persistence import (
    BrokerSessionRecord,
    EncryptedBrokerSessionStore,
)


NOW = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)


class FakeCipher:
    def encrypt(self, payload: bytes) -> bytes:
        return b"cipher:" + payload[::-1]

    def decrypt(self, payload: bytes) -> bytes:
        if not payload.startswith(b"cipher:"):
            raise ValueError("bad encrypted payload")
        return payload.removeprefix(b"cipher:")[::-1]


def record(*, token="access_token_secret", expires_at=None):
    return BrokerSessionRecord(
        broker="ZERODHA",
        user_id="AB1234",
        access_token=token,
        authenticated_at=NOW,
        expires_at=expires_at or NOW + timedelta(hours=6),
        created_at=NOW,
    )


def store(path, *, clock=lambda: NOW):
    return EncryptedBrokerSessionStore(path, cipher=FakeCipher(), clock=clock)


def test_session_save_restore_and_security_payload_excludes_plaintext_secrets(tmp_path):
    path = tmp_path / "broker_session.json"
    subject = store(path)

    snapshot = subject.save(record())
    restored = subject.load()

    payload_text = path.read_text(encoding="utf-8")
    payload = json.loads(payload_text)
    assert snapshot.token_valid is True
    assert restored == record()
    assert "encrypted_access_token" in payload
    assert "access_token_secret" not in payload_text
    assert "api_secret" not in payload_text
    assert "request_token" not in payload_text
    assert "password" not in payload_text
    assert "totp" not in payload_text
    assert "pin" not in payload_text


def test_expired_session_is_deleted_and_requires_login(tmp_path):
    path = tmp_path / "broker_session.json"
    subject = store(path, clock=lambda: NOW)
    subject.save(record(expires_at=NOW + timedelta(minutes=1)))

    expired = store(path, clock=lambda: NOW + timedelta(minutes=2))
    restored = expired.load()
    snapshot = expired.snapshot()

    assert restored is None
    assert path.exists() is False
    assert snapshot.token_valid is False
    assert snapshot.connection_state == "LOGIN_REQUIRED"
    assert "expired" in snapshot.blocking_reason.lower()


def test_corrupted_session_is_deleted_without_leaking_secret_material(tmp_path):
    path = tmp_path / "broker_session.json"
    path.write_text("not-json-access_token_secret", encoding="utf-8")
    subject = store(path)

    restored = subject.load()
    snapshot = subject.snapshot()

    assert restored is None
    assert path.exists() is False
    assert snapshot.authenticated is False
    assert "access_token_secret" not in snapshot.blocking_reason
