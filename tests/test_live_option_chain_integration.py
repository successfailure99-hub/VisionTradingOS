from datetime import date

from application.bootstrap import ApplicationBootstrap
from application.enums import ExecutionSafetyMode
from application.live_option_chain import LiveOptionChainRuntimeFactory
from brokers.zerodha.enums import BrokerExecutionMode
from core.event_bus import EventBus
from engines.option_chain.option_chain_engine import OptionChainEngine
from tests.test_live_option_chain_runtime import active_runtime, raw


def test_no_network_live_option_chain_flow_uses_existing_engine_only():
    runtime, manager, engine, transport = active_runtime()
    created = LiveOptionChainRuntimeFactory().create(
        universe=runtime._universe,
        subscription_manager=manager,
        option_chain_engine=OptionChainEngine(EventBus(), "NIFTY", "NSE", date(2026, 7, 30)),
        clock=runtime._clock,
    )
    created.start()
    created.set_underlying_price(25050, timestamp=runtime._clock())
    first = created.process_raw_ticks((raw(1, oi=100), raw(2, oi=200), raw(3, oi=300), raw(4, oi=400)))
    assert first.engine_updated is True
    assert created.snapshot().latest_option_chain_analysis.total_call_oi == 400
    second = created.process_raw_ticks((raw(1, oi=110), raw(2, oi=190), raw(3, oi=305), raw(4, oi=405)))
    assert second.engine_updated is True
    changes = {quote.instrument_token: quote.runtime_change_open_interest for quote in second.accepted_quotes}
    assert changes == {1: 10, 2: -10, 3: 5, 4: 5}
    assert all(call[0] != "connect" for call in transport.calls)
    assert engine.state is None
    app = ApplicationBootstrap().create_application()
    app_snapshot = app.snapshot().orchestrator_snapshot
    assert app_snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert app_snapshot.broker_mode is BrokerExecutionMode.DRY_RUN
