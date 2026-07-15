"""
Architecture checks for read-only dashboard live runtime integration.
"""

import ast
from dataclasses import fields
from pathlib import Path

from dashboard.models import DashboardLiveMarketDataView


PRODUCTION_PATHS = tuple(Path("dashboard").rglob("*.py")) + (Path("desktop_main.py"),)
FORBIDDEN_IMPORT_ROOTS = {
    "asyncio",
    "threading",
    "multiprocessing",
    "queue",
    "requests",
    "selenium",
    "playwright",
    "pyotp",
    "sqlite3",
    "websocket",
    "websockets",
    "kiteconnect",
}
FORBIDDEN_CALLS = {
    "Thread",
    "QThread",
    "start_new_thread",
    "create_task",
    "run_until_complete",
    "sleep",
    "fetch",
    "request",
    "calculate",
    "classify",
    "process_snapshot",
    "authenticate",
    "restore_session",
    "create_login_request",
    "login",
    "disconnect",
    "subscribe",
    "unsubscribe",
    "replace_subscriptions",
    "process_tick",
    "place_order",
    "submit_order",
    "open",
    "write_text",
    "write_bytes",
    "getenv",
}


def parse_all():
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in PRODUCTION_PATHS]


def call_name(node):
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def is_allowed_connect_call(node):
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "timeout"
    )


def test_dashboard_has_no_forbidden_imports_threads_or_network_calls():
    imports = set()
    calls = []
    for path, tree in parse_all():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.Call):
                name = call_name(node)
                if name == "connect" and is_allowed_connect_call(node):
                    continue
                calls.append((path, name))
    assert imports.isdisjoint(FORBIDDEN_IMPORT_ROOTS)
    forbidden = {(path.as_posix(), name) for path, name in calls if name in FORBIDDEN_CALLS or name == "connect"}
    assert forbidden == set()


def test_no_credentials_or_backend_owner_fields_in_live_dashboard_model():
    names = {field.name for field in fields(DashboardLiveMarketDataView)}
    assert names.isdisjoint(
        {
            "api_key",
            "api_secret",
            "access_token",
            "request_token",
            "session_manager",
            "websocket_manager",
            "client",
            "runtime_owner",
        }
    )


def test_dashboard_does_not_construct_live_runtime_or_websocket_manager():
    forbidden_names = {"ZerodhaSessionManager", "ZerodhaWebSocketManager", "LiveMarketDataRuntimeFactory"}
    constructed = set()
    for _, tree in parse_all():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                constructed.add(node.func.id)
    assert constructed.isdisjoint(forbidden_names)


def test_no_order_or_subscription_controls_and_no_private_backend_access():
    forbidden_text = {
        "Place Order",
        "Submit Order",
        "Subscribe",
        "Unsubscribe",
        "API Key",
        "Access Token",
    }
    private_backend_attrs = {"_websocket_manager", "_session_manager", "_configuration", "_client", "_session", "_runtimes"}
    for path in PRODUCTION_PATHS:
        text = path.read_text(encoding="utf-8")
        assert all(value not in text for value in forbidden_text)
        tree = ast.parse(text)
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert attrs.isdisjoint(private_backend_attrs)


def test_option_chain_dashboard_remains_presenter_driven_and_read_only():
    panel_text = Path("dashboard/panels/option_chain_panel.py").read_text(encoding="utf-8")
    presenter_text = Path("dashboard/presenters.py").read_text(encoding="utf-8")
    assert "engines.option_chain" not in panel_text
    assert "OptionChainEngine" not in panel_text
    assert "OptionChainAnalyticsEngine" not in panel_text
    assert "runtime_snapshot.option_chain" in presenter_text
    assert "OptionChainPanel" in Path("dashboard/main_window.py").read_text(encoding="utf-8")


def test_price_action_dashboard_remains_presenter_driven_and_read_only():
    panel_text = Path("dashboard/panels/price_action_panel.py").read_text(encoding="utf-8")
    presenter_text = Path("dashboard/presenters.py").read_text(encoding="utf-8")
    assert "engines.price_action" not in panel_text
    assert "PriceActionEngine" not in panel_text
    assert "runtime_snapshot.price_action" in presenter_text
    assert "PriceActionPanel" in Path("dashboard/main_window.py").read_text(encoding="utf-8")


def test_desktop_main_remains_offline():
    text = Path("desktop_main.py").read_text(encoding="utf-8")
    assert "LiveMarketDataRuntime" not in text
    assert "Zerodha" not in text
    assert "getenv" not in text
