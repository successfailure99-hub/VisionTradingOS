"""
Tests for safe Zerodha credential handling.
"""

from dataclasses import FrozenInstanceError, fields

import pytest

from brokers.zerodha.auth import ZerodhaCredentials


def test_valid_credentials_normalize_whitespace():
    credentials = ZerodhaCredentials("  api_key_1234  ", "  secret_value  ")

    assert credentials.api_key == "api_key_1234"
    assert credentials.api_secret == "secret_value"
    assert credentials.api_key_hint == "****1234"


def test_empty_api_key_rejected():
    with pytest.raises(ValueError):
        ZerodhaCredentials(" ", "secret")


def test_empty_api_secret_rejected():
    with pytest.raises(ValueError):
        ZerodhaCredentials("api_key", " ")


def test_credentials_are_immutable():
    credentials = ZerodhaCredentials("api_key", "secret")

    with pytest.raises(FrozenInstanceError):
        credentials.api_key = "other"


def test_repr_redacts_api_key_and_secret():
    credentials = ZerodhaCredentials("very_secret_key", "top_secret")

    representation = repr(credentials)

    assert "very_secret_key" not in representation
    assert "top_secret" not in representation
    assert "****_key" in representation
    assert "********" in representation


def test_str_redacts_secrets():
    credentials = ZerodhaCredentials("very_secret_key", "top_secret")

    text = str(credentials)

    assert "very_secret_key" not in text
    assert "top_secret" not in text


def test_model_has_no_password_pin_or_totp_fields():
    names = {field.name.lower() for field in fields(ZerodhaCredentials)}

    assert "password" not in names
    assert "pin" not in names
    assert "totp" not in names
    assert "totp_secret" not in names
