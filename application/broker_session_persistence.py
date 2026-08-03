"""
Encrypted broker session persistence owned by the application runtime.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from threading import RLock


BROKER_SESSION_STORE_VERSION = 1
DEFAULT_BROKER_SESSION_PATH = Path("runtime") / "broker_session.json"
SENSITIVE_KEYS = {"password", "pin", "totp", "api_secret", "request_token"}


def _now() -> datetime:
    return datetime.now(UTC)


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty text")
    return normalized


def _aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _optional_aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _aware(value, field_name)


def _parse_datetime(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text")
    parsed = datetime.fromisoformat(value)
    return _aware(parsed, field_name)


@dataclass(frozen=True, slots=True, repr=False)
class BrokerSessionRecord:
    broker: str
    user_id: str
    access_token: str
    authenticated_at: datetime
    expires_at: datetime | None
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "broker", _text(self.broker, "broker"))
        object.__setattr__(self, "user_id", _text(self.user_id, "user_id"))
        object.__setattr__(self, "access_token", _text(self.access_token, "access_token"))
        object.__setattr__(self, "authenticated_at", _aware(self.authenticated_at, "authenticated_at"))
        object.__setattr__(self, "expires_at", _optional_aware(self.expires_at, "expires_at"))
        object.__setattr__(self, "created_at", _aware(self.created_at, "created_at"))
        if self.expires_at is not None and self.expires_at <= self.authenticated_at:
            raise ValueError("expires_at must be later than authenticated_at")

    def __repr__(self) -> str:
        return (
            "BrokerSessionRecord("
            f"broker={self.broker!r}, "
            f"user_id={self.user_id!r}, "
            "access_token='[REDACTED]', "
            f"authenticated_at={self.authenticated_at!r}, "
            f"expires_at={self.expires_at!r}, "
            f"created_at={self.created_at!r})"
        )

    __str__ = __repr__

    def is_expired(self, timestamp: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        checked_at = _aware(timestamp or _now(), "timestamp")
        return checked_at >= self.expires_at


@dataclass(frozen=True, slots=True)
class BrokerSessionPersistenceSnapshot:
    broker: str
    store_path: str
    available: bool
    authenticated: bool
    token_valid: bool
    user_id: str | None
    created_at: datetime | None
    expires_at: datetime | None
    last_refresh: datetime | None
    connection_state: str
    blocking_reason: str = "-"

    def __post_init__(self) -> None:
        object.__setattr__(self, "broker", _text(self.broker, "broker"))
        object.__setattr__(self, "store_path", _text(self.store_path, "store_path"))
        for name in ("available", "authenticated", "token_valid"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")
        if self.user_id is not None:
            object.__setattr__(self, "user_id", _text(self.user_id, "user_id"))
        for name in ("created_at", "expires_at", "last_refresh"):
            object.__setattr__(self, name, _optional_aware(getattr(self, name), name))
        object.__setattr__(self, "connection_state", _text(self.connection_state, "connection_state"))
        object.__setattr__(self, "blocking_reason", _text(self.blocking_reason, "blocking_reason"))


class LocalMachineSessionCipher:
    """
    Windows DPAPI wrapper for local user encrypted session payloads.
    """

    def __init__(self, *, entropy: str = "VisionTradingOS:BrokerSession"):
        self._entropy = _text(entropy, "entropy").encode("utf-8")

    def encrypt(self, payload: bytes) -> bytes:
        return _crypt_protect(payload, self._entropy)

    def decrypt(self, payload: bytes) -> bytes:
        return _crypt_unprotect(payload, self._entropy)


class EncryptedBrokerSessionStore:
    def __init__(
        self,
        path: str | Path = DEFAULT_BROKER_SESSION_PATH,
        *,
        broker: str = "ZERODHA",
        cipher: LocalMachineSessionCipher | None = None,
        clock=None,
    ):
        self._path = Path(path)
        self._broker = _text(broker, "broker")
        self._cipher = cipher or LocalMachineSessionCipher(entropy=f"VisionTradingOS:{self._broker}")
        self._clock = clock or _now
        self._lock = RLock()
        self._last_record: BrokerSessionRecord | None = None
        self._last_refresh: datetime | None = None
        self._last_error: str | None = None

    @property
    def path(self) -> Path:
        return self._path

    def save(self, record: BrokerSessionRecord) -> BrokerSessionPersistenceSnapshot:
        if not isinstance(record, BrokerSessionRecord):
            raise TypeError("record must be BrokerSessionRecord")
        with self._lock:
            encrypted = self._cipher.encrypt(record.access_token.encode("utf-8"))
            payload = {
                "version": BROKER_SESSION_STORE_VERSION,
                "broker": record.broker,
                "user_id": record.user_id,
                "created_at": record.created_at.isoformat(),
                "authenticated_at": record.authenticated_at.isoformat(),
                "expires_at": record.expires_at.isoformat() if record.expires_at else None,
                "encrypted_access_token": base64.b64encode(encrypted).decode("ascii"),
            }
            self._assert_safe_payload(payload)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            self._last_record = record
            self._last_refresh = self._clock()
            self._last_error = None
            return self.snapshot()

    def load(self, *, delete_invalid: bool = True) -> BrokerSessionRecord | None:
        with self._lock:
            if not self._path.exists():
                self._last_record = None
                self._last_error = "Session file not found"
                return None
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                self._validate_payload(payload)
                encrypted = base64.b64decode(payload["encrypted_access_token"].encode("ascii"))
                access_token = self._cipher.decrypt(encrypted).decode("utf-8")
                record = BrokerSessionRecord(
                    broker=payload["broker"],
                    user_id=payload["user_id"],
                    access_token=access_token,
                    authenticated_at=_parse_datetime(payload["authenticated_at"], "authenticated_at"),
                    expires_at=_parse_datetime(payload.get("expires_at"), "expires_at"),
                    created_at=_parse_datetime(payload["created_at"], "created_at"),
                )
                if record.is_expired(self._clock()):
                    self.delete()
                    self._last_error = "Session token expired"
                    return None
                self._last_record = record
                self._last_refresh = self._clock()
                self._last_error = None
                return record
            except Exception as exc:
                self._last_record = None
                self._last_error = _safe_error(exc)
                if delete_invalid:
                    self.delete()
                return None

    def delete(self) -> BrokerSessionPersistenceSnapshot:
        with self._lock:
            try:
                if self._path.exists():
                    self._path.unlink()
            finally:
                self._last_record = None
                self._last_refresh = self._clock()
            return self.snapshot()

    def snapshot(self) -> BrokerSessionPersistenceSnapshot:
        with self._lock:
            record = self._last_record
            token_valid = bool(record is not None and not record.is_expired(self._clock()))
            return BrokerSessionPersistenceSnapshot(
                broker=self._broker,
                store_path=str(self._path),
                available=self._path.exists(),
                authenticated=bool(record is not None),
                token_valid=token_valid,
                user_id=record.user_id if record else None,
                created_at=record.created_at if record else None,
                expires_at=record.expires_at if record else None,
                last_refresh=self._last_refresh,
                connection_state="AUTHENTICATED" if token_valid else "LOGIN_REQUIRED",
                blocking_reason="-" if token_valid else (self._last_error or "No valid saved broker session"),
            )

    def _validate_payload(self, payload) -> None:
        if not isinstance(payload, dict):
            raise TypeError("session payload must be an object")
        if payload.get("version") != BROKER_SESSION_STORE_VERSION:
            raise ValueError("unsupported broker session version")
        required = {
            "broker",
            "user_id",
            "created_at",
            "authenticated_at",
            "encrypted_access_token",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError("missing broker session fields: " + ", ".join(missing))
        self._assert_safe_payload(payload)

    def _assert_safe_payload(self, payload: dict) -> None:
        lowered_keys = {str(key).casefold() for key in payload}
        if lowered_keys & SENSITIVE_KEYS:
            raise ValueError("broker session payload contains forbidden sensitive fields")
        rendered = json.dumps(payload, sort_keys=True).casefold()
        for forbidden in ("api_secret", "request_token", "password", "totp", "pin"):
            if forbidden in rendered:
                raise ValueError("broker session payload contains forbidden sensitive material")


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    for token in ("access_token", "api_secret", "request_token", "password", "totp", "pin"):
        text = text.replace(token, "[REDACTED]")
    return text[:500]


class _DATA_BLOB(ctypes.Structure):
    _fields_ = (("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char)))


def _blob_from_bytes(payload: bytes) -> tuple[_DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(payload, len(payload))
    return _DATA_BLOB(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _bytes_from_blob(blob: _DATA_BLOB) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def _crypt_protect(payload: bytes, entropy: bytes) -> bytes:
    data_blob, data_buffer = _blob_from_bytes(payload)
    entropy_blob, entropy_buffer = _blob_from_bytes(entropy)
    out_blob = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(data_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    _ = data_buffer, entropy_buffer
    if not ok:
        raise ctypes.WinError()
    return _bytes_from_blob(out_blob)


def _crypt_unprotect(payload: bytes, entropy: bytes) -> bytes:
    data_blob, data_buffer = _blob_from_bytes(payload)
    entropy_blob, entropy_buffer = _blob_from_bytes(entropy)
    out_blob = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(data_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    _ = data_buffer, entropy_buffer
    if not ok:
        raise ctypes.WinError()
    return _bytes_from_blob(out_blob)
