"""
Architecture checks for Zerodha authentication V1.
"""

import ast
from dataclasses import fields
from pathlib import Path

from brokers.zerodha.auth import ZerodhaAuthSnapshot, ZerodhaCredentials, ZerodhaSession


AUTH_ROOT = Path("brokers/zerodha/auth")


def auth_source_files():
    return sorted(AUTH_ROOT.glob("*.py"))


def parse(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def test_auth_source_rejects_forbidden_imports():
    forbidden = {
        "selenium",
        "playwright",
        "pyotp",
        "sqlite3",
        "PySide6",
        "websocket",
        "websockets",
    }
    imports = set()
    for path in auth_source_files():
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])

    assert imports.isdisjoint(forbidden)


def test_auth_source_rejects_forbidden_calls():
    forbidden = {
        "open",
        "write_text",
        "write_bytes",
        "login",
        "browser",
        "webdriver",
        "Thread",
        "create_task",
        "run_until_complete",
    }
    calls = set()
    for path in auth_source_files():
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)

    assert calls.isdisjoint(forbidden)


def test_public_snapshots_do_not_expose_secret_fields():
    snapshot_fields = {field.name for field in fields(ZerodhaAuthSnapshot)}

    assert "api_secret" not in snapshot_fields
    assert "access_token" not in snapshot_fields
    assert "request_token" not in snapshot_fields
    assert "password" not in snapshot_fields
    assert "pin" not in snapshot_fields
    assert "totp" not in snapshot_fields
    assert "totp_secret" not in snapshot_fields


def test_secret_dataclass_fields_are_limited_to_approved_models():
    credential_fields = {field.name for field in fields(ZerodhaCredentials)}
    session_fields = {field.name for field in fields(ZerodhaSession)}

    assert credential_fields == {"api_key", "api_secret"}
    assert "access_token" in session_fields
    assert "api_secret" not in session_fields
