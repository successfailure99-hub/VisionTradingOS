from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from application import RuntimeConfiguration
from application.lifecycle_manager import LifecycleSnapshot
from application.broker_account_sync import (
    BrokerAccountSnapshot,
    BrokerAccountSyncCoordinator,
    BrokerConnectionState,
    BrokerHoldingSnapshot,
    BrokerMutationMode,
    BrokerOrderStatusSnapshot,
    BrokerPositionSnapshot,
    BrokerReconciliationStatus,
    BrokerRuntimeStatus,
    BrokerSessionState,
)
from application.enums import RuntimeInstrument
from application.models import OrchestratorSnapshot, RuntimeSnapshot
from application.orchestrator import ApplicationOrchestrator
from brokers.zerodha.auth.enums import ZerodhaAuthStatus
from brokers.zerodha.auth.models import ZerodhaAuthSnapshot
from core.event_bus import EventBus
from dashboard.presenters import build_runtime_view
from tests.test_vision_paper_trading_integration_v1 import process, runtime as symbol_runtime
from tests.test_vision_method_validation_v1 import NOW, snapshot as method_snapshot

TS = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)
EXPIRES = datetime(2030, 1, 1, tzinfo=UTC)


def disabled_mutation(*args, **kwargs):
    raise RuntimeError("broker mutation disabled")


disabled_mutation.read_only_disabled = True


class FakeReadOnlyBrokerClient:
    account_id = "ABCD123456"
    user_id = "ABCD123456"
    place_order = disabled_mutation
    modify_order = disabled_mutation
    cancel_order = disabled_mutation
    exit_position = disabled_mutation

    def __init__(self):
        self.calls = []
        self.fail_next = False

    def margins(self):
        self.calls.append("margins")
        if self.fail_next:
            self.fail_next = False
            raise TimeoutError("network timeout without api_secret")
        return {"equity": {"available": 100000.0, "used": 25000.0}, "commodity": {"available": 5000.0, "used": 1000.0}}

    def positions(self):
        self.calls.append("positions")
        return [
            {
                "instrument": "NIFTY",
                "exchange": "NSE",
                "product": "MIS",
                "quantity": 1,
                "overnight_quantity": 0,
                "average_price": 100.0,
                "last_price": 103.0,
                "unrealized_pnl": 3.0,
                "realized_pnl": 0.0,
                "buy_quantity": 1,
                "sell_quantity": 0,
            }
        ]

    def holdings(self):
        self.calls.append("holdings")
        return [
            {
                "instrument": "NIFTYBEES",
                "exchange": "NSE",
                "quantity": 10,
                "t1_quantity": 0,
                "average_price": 220.0,
                "last_price": 225.0,
                "pnl": 50.0,
                "collateral_quantity": 0,
            }
        ]

    def orders(self):
        self.calls.append("orders")
        return [
            {
                "order_id": "order-1",
                "instrument": "NIFTY",
                "exchange": "NSE",
                "transaction_type": "BUY",
                "order_type": "MARKET",
                "product": "MIS",
                "quantity": 1,
                "filled_quantity": 1,
                "pending_quantity": 0,
                "average_price": 100.0,
                "status": "COMPLETE",
                "status_message": "filled",
                "created_at": TS,
                "updated_at": TS,
            }
        ]


class MutatingBrokerClient(FakeReadOnlyBrokerClient):
    def place_order(self, **kwargs):
        return "danger"


def auth(status=ZerodhaAuthStatus.AUTHENTICATED, *, expires_at=EXPIRES, last_error=None):
    return ZerodhaAuthSnapshot(
        status=status,
        user_id="ABCD123456",
        api_key_hint="****1234",
        authenticated_at=TS,
        expires_at=expires_at,
        last_error=last_error,
        login_url=None,
    )


def coordinator_with_client():
    client = FakeReadOnlyBrokerClient()
    coordinator = BrokerAccountSyncCoordinator()
    coordinator.configure_client(client)
    coordinator.observe_authentication(auth())
    return coordinator, client


def test_authenticated_account_snapshot_syncs_margins_positions_holdings_and_orders():
    coordinator, client = coordinator_with_client()

    account = coordinator.refresh(timestamp=TS, force=True)

    assert account.broker == "ZERODHA"
    assert account.account_id_masked == "****3456"
    assert account.authentication_state is BrokerSessionState.AUTHENTICATED
    assert account.connection_state is BrokerConnectionState.READY
    assert account.equity_available == 100000.0
    assert account.equity_used == 25000.0
    assert account.commodity_available == 5000.0
    assert account.total_available_margin == 105000.0
    assert len(account.positions) == 1
    assert len(account.holdings) == 1
    assert len(account.orders) == 1
    assert account.mutation_mode is BrokerMutationMode.DISABLED
    assert client.calls == ["margins", "positions", "holdings", "orders"]


def test_unauthenticated_and_token_expiry_are_explicit_without_fetching():
    coordinator = BrokerAccountSyncCoordinator()
    coordinator.configure_client(FakeReadOnlyBrokerClient())
    coordinator.observe_authentication(auth(ZerodhaAuthStatus.LOGGED_OUT, expires_at=None))
    unauthenticated = coordinator.refresh(timestamp=TS, force=True)

    assert unauthenticated.authentication_state is BrokerSessionState.UNAUTHENTICATED
    assert unauthenticated.blocking_reason == "Broker account sync requires authentication."

    coordinator.observe_authentication(auth(expires_at=TS - timedelta(seconds=1)))
    expired = coordinator.refresh(timestamp=TS, force=True)

    assert expired.authentication_state is BrokerSessionState.TOKEN_EXPIRED
    assert "token expired" in expired.blocking_reason.lower()


def test_last_valid_snapshot_is_preserved_as_stale_after_temporary_failure_and_recovers():
    coordinator, client = coordinator_with_client()
    first = coordinator.refresh(timestamp=TS, force=True)
    client.fail_next = True

    stale = coordinator.refresh(timestamp=TS + timedelta(seconds=10), force=True)

    assert stale.is_stale is True
    assert stale.positions == first.positions
    assert stale.holdings == first.holdings
    assert stale.orders == first.orders
    assert stale.data_age == 10.0
    assert coordinator.retry_count == 1

    recovered = coordinator.refresh(timestamp=TS + timedelta(seconds=20), force=True)

    assert recovered.is_stale is False
    assert recovered.data_age == 0.0
    assert coordinator.retry_count == 0


def test_duplicate_refresh_is_suppressed_by_policy_without_fetch_storm():
    coordinator, client = coordinator_with_client()
    coordinator.refresh(timestamp=TS, force=True)
    first_call_count = len(client.calls)

    same = coordinator.refresh(timestamp=TS + timedelta(seconds=1), force=False)

    assert same.latest_refresh_timestamp == TS
    assert len(client.calls) == first_call_count


def test_malformed_payload_does_not_replace_last_valid_snapshot():
    coordinator, client = coordinator_with_client()
    first = coordinator.refresh(timestamp=TS, force=True)
    client.positions = lambda: {"bad": "payload"}

    stale = coordinator.refresh(timestamp=TS + timedelta(seconds=30), force=True)

    assert stale.is_stale is True
    assert stale.positions == first.positions
    assert "positions payload" in stale.blocking_reason


def test_nested_models_are_immutable_and_sensitive_fields_are_rejected():
    position = BrokerPositionSnapshot("NIFTY", "NSE", "MIS", 1, 0, 100.0, 101.0, 1.0, 0.0, 1, 0)
    holding = BrokerHoldingSnapshot("NIFTYBEES", "NSE", 1, 0, 100.0, 101.0, 1.0, 0)
    order = BrokerOrderStatusSnapshot("order-1", "NIFTY", "NSE", "BUY", "MARKET", "MIS", 1, 1, 0, 100.0, "COMPLETE", None, TS, TS)

    with pytest.raises(FrozenInstanceError):
        position.quantity = 2
    with pytest.raises(FrozenInstanceError):
        holding.quantity = 2
    with pytest.raises(FrozenInstanceError):
        order.status = "OPEN"
    with pytest.raises(ValueError, match="sensitive"):
        BrokerOrderStatusSnapshot("access_token=secret", "NIFTY", "NSE", "BUY", "MARKET", "MIS", 1, 1, 0, 100.0, "COMPLETE", None, TS, TS)


def test_runtime_orchestrator_owns_one_shared_account_state_not_per_symbol():
    orchestrator = ApplicationOrchestrator(EventBus(), RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY)))
    orchestrator.start()
    client = FakeReadOnlyBrokerClient()
    orchestrator.configure_broker_account_client(client)
    orchestrator.observe_broker_authentication(auth())

    account = orchestrator.refresh_broker_account(timestamp=TS, force=True)
    view = orchestrator.snapshot()

    assert view.broker_account is account
    assert view.runtime_snapshots
    assert all(not hasattr(runtime_snapshot, "broker_account") for runtime_snapshot in view.runtime_snapshots)
    assert isinstance(view, OrchestratorSnapshot)
    assert all(isinstance(runtime_snapshot, RuntimeSnapshot) for runtime_snapshot in view.runtime_snapshots)


def test_runtime_verification_rows_and_dashboard_panel_read_snapshot_only():
    orchestrator = ApplicationOrchestrator(EventBus(), RuntimeConfiguration())
    orchestrator.start()
    orchestrator.configure_broker_account_client(FakeReadOnlyBrokerClient())
    orchestrator.observe_broker_authentication(auth())
    orchestrator.refresh_broker_account(timestamp=TS, force=True)

    snapshot = orchestrator.snapshot()
    stages = {stage.stage: stage for stage in snapshot.broker_account_verification_report}
    runtime_view = build_runtime_view(
        LifecycleSnapshot(
            status=snapshot.status,
            start_count=1,
            stop_count=0,
            restart_count=0,
            last_started_at=TS,
            last_stopped_at=None,
            last_error=None,
            orchestrator_snapshot=snapshot,
        )
    )
    rows = {row.name: row for row in runtime_view.component_health}

    assert stages["BROKER_AUTH"].status is BrokerRuntimeStatus.READY
    assert stages["BROKER_ACCOUNT_SYNC"].status is BrokerRuntimeStatus.READY
    assert stages["BROKER_MUTATION_MODE"].status is BrokerRuntimeStatus.DISABLED
    assert rows["BROKER_MARGINS"].status == "READY"
    assert runtime_view.broker_account_broker == "ZERODHA"
    assert runtime_view.broker_account_id == "****3456"
    assert runtime_view.broker_available_margin == 105000.0
    assert runtime_view.broker_used_margin == 26000.0
    assert runtime_view.broker_open_positions == 1
    assert runtime_view.broker_holdings_count == 1
    assert runtime_view.broker_orders_count == 1
    assert runtime_view.broker_mutation_mode == "DISABLED"


def test_mutation_methods_are_unreachable_from_account_sync_and_dashboard():
    coordinator = BrokerAccountSyncCoordinator()
    coordinator.configure_client(MutatingBrokerClient())
    coordinator.observe_authentication(auth())

    blocked = coordinator.refresh(timestamp=TS, force=True)

    assert blocked.is_stale is False
    assert "mutation method" in blocked.blocking_reason
    dashboard_source = "\n".join(path.read_text(encoding="utf-8") for path in Path("dashboard").rglob("*.py"))
    assert ".margins(" not in dashboard_source
    assert ".positions(" not in dashboard_source
    assert ".holdings(" not in dashboard_source
    assert ".orders(" not in dashboard_source
    assert "place_order" not in dashboard_source
    assert "modify_order" not in dashboard_source
    assert "cancel_order" not in dashboard_source
    assert "exit_position" not in dashboard_source


def test_paper_broker_reconciliation_statuses_are_observable():
    item = symbol_runtime()
    process(item, method_snapshot())
    paper = item.snapshot().canonical_paper_position
    coordinator, _ = coordinator_with_client()
    account = coordinator.refresh(timestamp=TS, force=True)

    matched = coordinator.reconcile_paper_position(paper)
    no_broker = BrokerAccountSyncCoordinator().reconcile_paper_position(paper)

    assert account.reconciliation.reconciliation_status is BrokerReconciliationStatus.NOT_APPLICABLE
    assert matched.reconciliation_status in {BrokerReconciliationStatus.MATCHED, BrokerReconciliationStatus.MISMATCHED}
    assert no_broker.reconciliation_status is BrokerReconciliationStatus.BROKER_UNAVAILABLE


def test_shutdown_during_refresh_suppression_and_reset_are_safe():
    orchestrator = ApplicationOrchestrator(EventBus(), RuntimeConfiguration())
    orchestrator.start()
    orchestrator.configure_broker_account_client(FakeReadOnlyBrokerClient())
    orchestrator.observe_broker_authentication(auth())
    orchestrator.refresh_broker_account(timestamp=TS, force=True)

    stopped = orchestrator.stop()
    reset = orchestrator.reset_zerodha_adapter()

    assert stopped.broker_account.latest_refresh_timestamp == TS
    assert reset.enabled is False or reset.connected is False
    assert orchestrator.get_broker_account_snapshot().latest_refresh_timestamp is None