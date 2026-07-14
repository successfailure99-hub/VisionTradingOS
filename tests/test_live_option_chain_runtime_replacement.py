from datetime import date

import pytest

from application.live_option_chain import LiveOptionChainStatus
from tests.test_live_option_chain_assembler import universe
from tests.test_live_option_chain_runtime import active_runtime, raw, NOW


def test_replace_requires_subscription_manager_match_and_resets_state():
    runtime, manager, engine, _ = active_runtime()
    runtime.start()
    runtime.set_underlying_price(25050, timestamp=NOW)
    runtime.process_raw_ticks((raw(1), raw(2), raw(3), raw(4)))
    assert engine.state is not None
    manager.replace(universe())
    snapshot = runtime.replace_universe(universe())
    assert snapshot.status is LiveOptionChainStatus.COLLECTING
    assert snapshot.quoted_token_count == 0
    assert snapshot.engine_update_count == 1
    assert engine.state is None


def test_failed_replacement_preserves_old_runtime_and_no_subscription_replace_call():
    runtime, _, _, transport = active_runtime()
    before = runtime.snapshot()
    bad = universe()
    object.__setattr__(bad, "subscriptions", bad.subscriptions[:-1])
    with pytest.raises(Exception):
        runtime.replace_universe(bad)
    after = runtime.snapshot()
    assert after.underlying == before.underlying
    assert not any(call[0] == "subscribe" for call in transport.calls[len(transport.calls):])
