from datetime import timedelta

from core.enums.instrument import Instrument
from engines.strategy_decision_v2 import StrategyDecisionChange, StrategyDecisionV2Engine, StrategyDecisionV2Input
from tests.test_strategy_decision_v2_integration import build_stack, cam, cpr, replace_context, vwap


def inp(reasoning):
    return StrategyDecisionV2Input(reasoning, 108.0, cam(), cpr(), vwap())


def test_chronological_direction_and_confidence_transitions():
    engine = StrategyDecisionV2Engine(instrument=Instrument.NIFTY)
    first = engine.process(inp(build_stack("insufficient")))
    assert first.change is StrategyDecisionChange.INITIAL
    long = engine.process(inp(replace_context(build_stack("bullish"), timestamp=first.timestamp + timedelta(minutes=1))))
    assert long.change is StrategyDecisionChange.SETUP_APPEARED
    stronger = engine.process(inp(replace_context(build_stack("bullish"), timestamp=first.timestamp + timedelta(minutes=2), confidence=0.9)))
    assert stronger.change in {StrategyDecisionChange.SETUP_STRENGTHENED, StrategyDecisionChange.UNCHANGED}
    short = engine.process(inp(replace_context(build_stack("bearish"), timestamp=first.timestamp + timedelta(minutes=3))))
    assert short.change is StrategyDecisionChange.TURNED_SHORT


def test_same_timestamp_correction_preserves_previous_distinct_state():
    engine = StrategyDecisionV2Engine(instrument=Instrument.NIFTY)
    first_reasoning = build_stack("insufficient")
    first = engine.process(inp(first_reasoning))
    second_reasoning = replace_context(build_stack("bullish"), timestamp=first.timestamp + timedelta(minutes=1))
    second = engine.process(inp(second_reasoning))
    corrected = engine.process(inp(replace_context(build_stack("bearish"), timestamp=second.timestamp)))
    assert engine.previous_snapshot is first
    assert len(engine.history()) == 2
    assert corrected.change is StrategyDecisionChange.SETUP_APPEARED
