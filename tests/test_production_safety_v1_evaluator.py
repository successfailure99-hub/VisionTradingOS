from datetime import timedelta

from core.enums.instrument import Instrument
from engines.production_safety_v1 import (
    ProductionSafetyEvaluator,
    ProductionSafetyV1Configuration,
    SafetyDecision,
    SafetyRuleType,
)
from tests.test_market_context_v2_integration import NOW
from tests.test_production_safety_v1_integration import safety_input


def test_evaluator_healthy_manual_limits_active_state_and_market_data():
    evaluator = ProductionSafetyEvaluator()
    config = ProductionSafetyV1Configuration()

    healthy = evaluator.evaluate(safety_input(), config, manual_global_lock=False, manual_instrument_locks=())
    assert all(item.decision is SafetyDecision.ALLOW for item in healthy)

    manual = evaluator.evaluate(safety_input(), config, manual_global_lock=True, manual_instrument_locks=(Instrument.NIFTY,))
    assert any(item.rule is SafetyRuleType.MANUAL_KILL_SWITCH and item.decision is SafetyDecision.BLOCK_GLOBAL for item in manual)
    assert any(item.instrument is Instrument.NIFTY and item.decision is SafetyDecision.BLOCK_INSTRUMENT for item in manual)

    loss = evaluator.evaluate(safety_input(realized=-250.0), config, manual_global_lock=False, manual_instrument_locks=())
    assert any(item.rule is SafetyRuleType.DAILY_LOSS_LIMIT and item.decision is SafetyDecision.BLOCK_GLOBAL for item in loss)

    stale = evaluator.evaluate(safety_input(market_data_age=timedelta(seconds=35)), config, manual_global_lock=False, manual_instrument_locks=())
    assert any(item.rule is SafetyRuleType.MARKET_DATA_STALENESS and item.instrument is Instrument.NIFTY and item.decision is SafetyDecision.BLOCK_INSTRUMENT for item in stale)
