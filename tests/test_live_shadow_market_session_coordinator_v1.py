from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from adapters.zerodha import ZerodhaConnectionState, ZerodhaCredentials, ZerodhaReadOnlyAdapter
from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from application.live_shadow_session import (
    LiveShadowMarketSessionCoordinator,
    LiveShadowSessionReport,
    LiveShadowSessionRequest,
    LiveShadowSessionSnapshot,
    LiveShadowSessionState,
    LiveShadowSessionStatus,
)
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.models.tick import Tick
from engines.shadow_trading_session.enums import ShadowSessionLifecycleState, ShadowSessionStatus
from engines.shadow_trading_session.models import ShadowTradingSessionSummary


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 7, 20, 9, 30, tzinfo=IST)
LATER = datetime(2026, 7, 20, 15, 20, tzinfo=IST)


def record(token, symbol, name, exchange):
    return {
        "instrument_token": token,
        "exchange_token": token + 1000,
        "tradingsymbol": symbol,
        "name": name,
        "exchange": exchange,
        "segment": f"{exchange}-INDICES",
        "instrument_type": "INDEX",
        "expiry": None,
        "strike": None,
        "lot_size": None,
        "tick_size": 0.05,
    }


class AuthClient:
    def set_access_token(self, access_token):
        self.access_token = access_token

    def profile(self):
        return {"user_id": "USER1"}


class InstrumentClient:
    def instruments(self, exchange):
        return {
            "NSE": (
                record(101, "NIFTY 50", "NIFTY 50", "NSE"),
                record(201, "NIFTY BANK", "NIFTY BANK", "NSE"),
            ),
            "BSE": (record(301, "SENSEX", "SENSEX", "BSE"),),
        }[exchange]


class TickerClient:
    def __init__(self):
        self.callbacks = {}
        self.connect_calls = 0
        self.close_calls = 0
        self.subscribed = []
        self.modes = []

    def set_callbacks(self, **callbacks):
        self.callbacks = callbacks

    def connect(self, *, threaded=False):
        self.connect_calls += 1
        self.threaded = threaded

    def close(self):
        self.close_calls += 1

    def subscribe(self, instrument_tokens):
        self.subscribed.append(list(instrument_tokens))

    def set_mode(self, mode, instrument_tokens):
        self.modes.append((mode, list(instrument_tokens)))


def raw_tick(token=101, price=22000.5, timestamp=NOW):
    return {
        "instrument_token": token,
        "last_price": price,
        "exchange_timestamp": timestamp,
        "volume_traded": 100,
        "oi": 10,
        "depth": {
            "buy": [{"price": price - 0.5}],
            "sell": [{"price": price + 0.5}],
        },
    }


def tick(symbol=Instrument.NIFTY, price=22000.5, timestamp=NOW):
    exchange = Exchange.BSE if symbol is Instrument.SENSEX else Exchange.NSE
    return Tick(
        symbol=symbol,
        exchange=exchange,
        timestamp=timestamp,
        last_price=price,
        volume=100,
        bid_price=price - 0.5,
        ask_price=price + 0.5,
        open_interest=10,
    )


def configured_app(instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.SENSEX)):
    bus = EventBus()
    app = ApplicationOrchestrator(bus, RuntimeConfiguration(instruments=instruments))
    ticker = TickerClient()
    app.zerodha_adapter = ZerodhaReadOnlyAdapter(
        bus,
        auth_client=AuthClient(),
        instrument_client=InstrumentClient(),
        ticker_client=ticker,
        tick_consumer=app.process_live_zerodha_tick,
        clock=lambda: NOW,
    )
    app.start()
    app.start_live_shadow_coordinator()
    app.configure_zerodha_credentials(ZerodhaCredentials("api", "token"))
    app.load_zerodha_instrument_tokens()
    app.connect_zerodha_market_data()
    app.zerodha_adapter.on_connect(None, None)
    return app, ticker


def request(session_id="session-1", instruments=("NIFTY", "BANKNIFTY", "SENSEX")):
    return LiveShadowSessionRequest(
        session_id=session_id,
        started_at=NOW,
        instruments=instruments,
        correlation_id="corr-1",
        metadata=(("source", "test"),),
    )


def reconnect_zerodha(app):
    app.connect_zerodha_market_data()
    app.zerodha_adapter.on_connect(None, None)


def summary(instrument, status=ShadowSessionStatus.HEALTHY, reason="session_completed"):
    return ShadowTradingSessionSummary(
        session_id=f"session-1:{instrument.value}",
        started_at=NOW,
        ended_at=LATER,
        instrument=instrument.value,
        lifecycle_state=ShadowSessionLifecycleState.COMPLETED,
        session_status=status,
        primary_reason=reason,
        market_event_count=0,
        execution_plan_count=0,
        approved_plan_count=0,
        rejected_plan_count=1 if status is ShadowSessionStatus.BLOCKED else 0,
        paper_receipt_count=0,
        paper_completed_count=0,
        paper_cancelled_count=0,
        paper_failed_count=0,
        reconciliation_report_count=0,
        consistent_reconciliation_count=0,
        warning_reconciliation_count=1 if status is ShadowSessionStatus.HEALTHY_WITH_WARNINGS else 0,
        incomplete_reconciliation_count=0,
        inconsistent_reconciliation_count=1 if status is ShadowSessionStatus.DEGRADED else 0,
        invalid_reconciliation_count=0,
        failed_reconciliation_count=0,
        position_open_count=0,
        position_closed_count=0,
        observations=(),
        latest_execution_plan_id=None,
        latest_execution_receipt_id=None,
        latest_reconciliation_report_id=None,
        latest_position_id=None,
        correlation_id="corr-1",
    )


def test_models_are_immutable_validate_time_instruments_metadata_and_fingerprints():
    req = request(instruments=("SENSEX", "NIFTY"))
    assert req.instruments == ("NIFTY", "SENSEX")
    assert req.fingerprint() == request(instruments=("NIFTY", "SENSEX")).fingerprint()
    with pytest.raises(FrozenInstanceError):
        req.session_id = "x"
    with pytest.raises(ValueError):
        LiveShadowSessionRequest("s", datetime(2026, 7, 20), ("NIFTY",))
    with pytest.raises(ValueError):
        LiveShadowSessionRequest("s", NOW, ())
    with pytest.raises(ValueError):
        LiveShadowSessionRequest("s", NOW, ("FINNIFTY",))
    with pytest.raises(ValueError):
        LiveShadowSessionRequest("s", NOW, ("NIFTY", "nifty"))
    report = LiveShadowSessionReport(
        session_id="s",
        started_at=NOW,
        ended_at=LATER,
        state=LiveShadowSessionState.COMPLETED,
        status=LiveShadowSessionStatus.HEALTHY,
        primary_reason="done",
        instruments=(RuntimeInstrument.NIFTY,),
        instrument_results=(),
        zerodha_state=ZerodhaConnectionState.DISCONNECTED,
        zerodha_authenticated=True,
        zerodha_connected=False,
        zerodha_received_tick_count=0,
        zerodha_published_tick_count=0,
        zerodha_rejected_tick_count=0,
        zerodha_duplicate_tick_count=0,
        total_market_tick_count=0,
        total_accepted_tick_count=0,
        total_rejected_tick_count=0,
        total_shadow_observation_count=0,
    )
    with pytest.raises(FrozenInstanceError):
        report.primary_reason = "x"
    snap = LiveShadowSessionSnapshot(
        enabled=True,
        state=LiveShadowSessionState.CREATED,
        active_session_id=None,
        active_instruments=(),
        started_at=None,
        last_tick_at=None,
        market_tick_count=0,
        accepted_tick_count=0,
        rejected_tick_count=0,
        shadow_observation_count=0,
        last_report=None,
        failure_code=None,
    )
    with pytest.raises(FrozenInstanceError):
        snap.enabled = False


def test_lifecycle_start_duplicate_stop_terminal_reset_and_one_shadow_per_instrument():
    app, ticker = configured_app()
    coordinator = app.live_shadow_session_coordinator
    assert coordinator.snapshot().state is LiveShadowSessionState.READY
    started = app.start_live_shadow_session(request())
    assert started.state is LiveShadowSessionState.RUNNING
    assert started.active_instruments == (RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.SENSEX)
    assert ticker.connect_calls == 1
    assert ticker.subscribed == [[101, 201, 301]]
    duplicate = app.start_live_shadow_session(request())
    assert duplicate == started
    assert ticker.subscribed == [[101, 201, 301]]
    with pytest.raises(ValueError):
        app.start_live_shadow_session(request("session-2"))
    report = app.stop_live_shadow_session(timestamp=LATER)
    assert report.state is LiveShadowSessionState.COMPLETED
    assert report.status is LiveShadowSessionStatus.HEALTHY
    assert app.stop_live_shadow_session(timestamp=LATER) == report
    assert app.get_live_shadow_report("session-1") == report
    with pytest.raises(RuntimeError):
        app.start_live_shadow_session(request("session-3"))
    assert app.reset_live_shadow_coordinator().state is LiveShadowSessionState.READY
    reconnect_zerodha(app)
    app.start_live_shadow_session(request("session-3", ("NIFTY",)))
    assert app.get_live_shadow_snapshot().active_instruments == (RuntimeInstrument.NIFTY,)


def test_startup_safety_auth_connection_subscription_partial_cleanup_and_configuration():
    app, _ = configured_app((RuntimeInstrument.NIFTY,))
    with pytest.raises(ValueError):
        app.start_live_shadow_session(request(instruments=("BANKNIFTY",)))
    app, _ = configured_app()
    app.zerodha_adapter.reset()
    snap = app.start_live_shadow_session(request("unauth"))
    assert snap.state is LiveShadowSessionState.FAILED
    assert "not_authenticated" in snap.failure_code or "authenticated" in snap.failure_code
    assert app.zerodha_adapter.snapshot().subscribed_instruments == ()
    app, _ = configured_app()
    app.disconnect_zerodha_market_data()
    snap = app.start_live_shadow_session(request("disc"))
    assert snap.state is LiveShadowSessionState.FAILED
    assert app.zerodha_adapter.snapshot().subscribed_instruments == ()
    app, _ = configured_app()
    original_start = app.start_shadow_session
    original_stop = app.stop_shadow_session
    starts = []
    stops = []

    def fail_second(instrument, shadow_request):
        starts.append(instrument)
        if instrument is RuntimeInstrument.BANKNIFTY:
            raise RuntimeError("shadow boom")
        return original_start(instrument, shadow_request)

    def spy_stop(instrument, *, timestamp, reason="session_completed"):
        stops.append((instrument, reason))
        return original_stop(instrument, timestamp=timestamp, reason=reason)

    app.start_shadow_session = fail_second
    app.stop_shadow_session = spy_stop
    snap = app.start_live_shadow_session(request("partial"))
    assert snap.state is LiveShadowSessionState.FAILED
    assert starts == [RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY]
    assert stops == [(RuntimeInstrument.NIFTY, "startup_failed")]
    assert app.zerodha_adapter.snapshot().subscribed_instruments == ()


def test_live_zerodha_tick_routing_counts_once_dedupes_and_excludes_manual_ticks():
    app, _ = configured_app()
    app.start_live_shadow_session(request())
    app.zerodha_adapter.on_ticks(None, (raw_tick(101, 22000.5),))
    snap = app.get_live_shadow_snapshot()
    assert snap.market_tick_count == 1
    assert snap.accepted_tick_count == 1
    assert snap.shadow_observation_count == 1
    assert snap.last_tick_at == NOW
    app.zerodha_adapter.on_ticks(None, (raw_tick(101, 22000.5),))
    assert app.get_live_shadow_snapshot() == snap
    app.process_tick(tick(Instrument.BANKNIFTY, 51000.0, NOW.replace(minute=31)))
    assert app.get_live_shadow_snapshot() == snap
    app.live_shadow_session_coordinator.observe_tick(tick(Instrument.SENSEX, 80000.0, NOW.replace(minute=32)), accepted=False)
    rejected = app.get_live_shadow_snapshot()
    assert rejected.market_tick_count == 2
    assert rejected.accepted_tick_count == 1
    assert rejected.rejected_tick_count == 1
    assert rejected.shadow_observation_count == 1
    app.stop_live_shadow_session(timestamp=LATER)
    completed = app.get_live_shadow_snapshot()
    app.zerodha_adapter.on_ticks(None, (raw_tick(201, 51000.0, NOW.replace(minute=33)),))
    assert app.get_live_shadow_snapshot() == completed


def test_tick_routes_only_matching_active_instrument_shadow_session():
    app, _ = configured_app()
    app.start_live_shadow_session(request(instruments=("NIFTY", "BANKNIFTY")))
    calls = []
    original = app.observe_shadow_event

    def spy(instrument, event_name, payload, *, timestamp):
        calls.append((instrument, event_name, payload.symbol))
        return original(instrument, event_name, payload, timestamp=timestamp)

    app.observe_shadow_event = spy
    app.live_shadow_session_coordinator.observe_tick(tick(Instrument.NIFTY), accepted=True)
    app.live_shadow_session_coordinator.observe_tick(tick(Instrument.BANKNIFTY, 51000.0, NOW.replace(minute=31)), accepted=True)
    app.live_shadow_session_coordinator.observe_tick(tick(Instrument.SENSEX, 80000.0, NOW.replace(minute=32)), accepted=True)
    assert calls == [
        (RuntimeInstrument.NIFTY, "new_tick", Instrument.NIFTY),
        (RuntimeInstrument.BANKNIFTY, "new_tick", Instrument.BANKNIFTY),
    ]


def test_connection_health_failure_late_ticks_and_no_reconnect():
    app, ticker = configured_app()
    app.start_live_shadow_session(request())
    assert app.observe_live_shadow_zerodha_state().state is LiveShadowSessionState.RUNNING
    app.zerodha_adapter.on_close(None, 1000, "closed")
    assert app.observe_live_shadow_zerodha_state().state is LiveShadowSessionState.RUNNING
    report = app.stop_live_shadow_session(timestamp=LATER)
    assert report.status is LiveShadowSessionStatus.DEGRADED
    app.reset_live_shadow_coordinator()
    app.zerodha_adapter.reset()
    app.configure_zerodha_credentials(ZerodhaCredentials("api", "token"))
    app.load_zerodha_instrument_tokens()
    app.connect_zerodha_market_data()
    app.zerodha_adapter.on_connect(None, None)
    app.start_live_shadow_session(request("fail"))
    app.zerodha_adapter.on_error(None, "boom", "bad")
    failed = app.observe_live_shadow_zerodha_state()
    assert failed.state is LiveShadowSessionState.FAILED
    app.live_shadow_session_coordinator.observe_tick(tick(), accepted=True)
    assert app.get_live_shadow_snapshot() == failed
    with pytest.raises(RuntimeError):
        app.start_live_shadow_session(request("again"))
    assert ticker.connect_calls == 2


def test_final_report_status_priority_counters_failed_report_and_duplicate_events():
    app, _ = configured_app()
    completed_events = []
    app._event_bus.subscribe("live_shadow_session_completed", completed_events.append)
    statuses = {
        RuntimeInstrument.NIFTY: ShadowSessionStatus.HEALTHY_WITH_WARNINGS,
        RuntimeInstrument.BANKNIFTY: ShadowSessionStatus.HEALTHY,
        RuntimeInstrument.SENSEX: ShadowSessionStatus.HEALTHY,
    }
    app.stop_shadow_session = lambda instrument, *, timestamp, reason="session_completed": summary(instrument, statuses[instrument])
    app.start_live_shadow_session(request("warn"))
    app.live_shadow_session_coordinator.observe_tick(tick(), accepted=True)
    report = app.stop_live_shadow_session(timestamp=LATER)
    assert report.status is LiveShadowSessionStatus.HEALTHY_WITH_WARNINGS
    assert report.total_market_tick_count == 1
    assert report.total_accepted_tick_count == 1
    assert report.total_shadow_observation_count == 1
    assert len(report.instrument_results) == 3
    assert app.stop_live_shadow_session(timestamp=LATER) == report
    assert len(completed_events) == 1

    app, _ = configured_app()
    statuses = {instrument: ShadowSessionStatus.BLOCKED for instrument in statuses}
    app.stop_shadow_session = lambda instrument, *, timestamp, reason="session_completed": summary(instrument, statuses[instrument])
    app.start_live_shadow_session(request("blocked"))
    assert app.stop_live_shadow_session(timestamp=LATER).status is LiveShadowSessionStatus.BLOCKED

    app, _ = configured_app()
    statuses = {RuntimeInstrument.NIFTY: ShadowSessionStatus.DEGRADED}
    app.stop_shadow_session = lambda instrument, *, timestamp, reason="session_completed": summary(instrument, statuses[instrument])
    app.start_live_shadow_session(request("degraded", ("NIFTY",)))
    assert app.stop_live_shadow_session(timestamp=LATER).status is LiveShadowSessionStatus.DEGRADED

    app, _ = configured_app()
    app.start_live_shadow_session(request("failed", ("NIFTY",)))
    app.live_shadow_session_coordinator._fail("coordinator_failure")
    failed = app.stop_live_shadow_session(timestamp=LATER)
    assert failed.state is LiveShadowSessionState.FAILED
    assert failed.status is LiveShadowSessionStatus.FAILED


def test_orchestrator_integration_snapshot_facades_and_reset_stop_states():
    app, _ = configured_app()
    assert app.snapshot().live_shadow_session.state is LiveShadowSessionState.READY
    assert app.get_live_shadow_snapshot() == app.live_shadow_session_coordinator.snapshot()
    app.start_live_shadow_session(request("complete", ("NIFTY",)))
    app.stop_live_shadow_session(timestamp=LATER)
    with pytest.raises(RuntimeError):
        app.start_live_shadow_session(request("no-restart", ("NIFTY",)))
    assert app.reset_live_shadow_coordinator().state is LiveShadowSessionState.READY
    app.live_shadow_session_coordinator.stop()
    with pytest.raises(RuntimeError):
        app.start_live_shadow_session(request("stopped", ("NIFTY",)))
    assert app.reset_live_shadow_coordinator().state is LiveShadowSessionState.READY


def test_read_only_safety_no_forbidden_calls_workers_timers_or_broker_mutation():
    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("application/live_shadow_session").glob("*.py"))
    forbidden = (
        "place_order",
        "modify_order",
        "cancel_order",
        "execute_paper_plan",
        "reconcile_paper_execution",
        "apply_position",
        "threading",
        "asyncio",
        "time.sleep",
        "QTimer",
        "EventBus(",
    )
    for item in forbidden:
        assert item not in text
    app, _ = configured_app()
    snapshot = app.get_live_shadow_snapshot()
    assert snapshot.broker_order_calls == 0
    assert snapshot.mutation_calls == 0
    assert snapshot.live_order_submission_enabled is False
