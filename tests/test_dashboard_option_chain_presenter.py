"""
Tests for dashboard option-chain presenters.
"""

from datetime import UTC, date, datetime

from application.enums import ExecutionSafetyMode, RuntimeInstrument, RuntimeStatus
from application.lifecycle_manager import LifecycleSnapshot
from application.models import OrchestratorSnapshot, RuntimeSnapshot
from brokers.zerodha.enums import BrokerExecutionMode
from dashboard.presenters import build_dashboard_view, build_option_chain_view
from engines.option_chain.enums import OptionType, PositioningBias, PressureType
from engines.option_chain.models import OptionChainState, OptionLeg, OptionStrike, StrikeMetric


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def leg(option_type, last_price, oi, change_oi, volume, bid=None, ask=None):
    return OptionLeg(option_type, last_price, oi, change_oi, volume, bid, ask)


def call(last_price=10.0, oi=100, change_oi=5, volume=20):
    return leg(OptionType.CALL, last_price, oi, change_oi, volume, 9.5, 10.5)


def put(last_price=8.0, oi=120, change_oi=-7, volume=30):
    return leg(OptionType.PUT, last_price, oi, change_oi, volume, 7.5, 8.5)


def state(symbol="NIFTY", strikes=None):
    strikes = tuple(strikes or (
        OptionStrike(110.0, call(11.0, 180, 15, 40), put(5.0, 80, -2, 15)),
        OptionStrike(90.0, call(18.0, 60, -4, 10), put(12.0, 220, 25, 50)),
        OptionStrike(100.0, call(), put()),
    ))
    return OptionChainState(
        symbol=symbol,
        exchange="NSE",
        expiry_date=date(2026, 7, 30),
        timestamp=NOW,
        underlying_price=101.0,
        atm_strike=100.0,
        strike_count=len(strikes),
        total_call_oi=340,
        total_put_oi=420,
        total_call_change_oi=16,
        total_put_change_oi=16,
        oi_pcr=1.235,
        change_oi_pcr=1.0,
        max_call_oi=StrikeMetric(110.0, 180),
        max_put_oi=StrikeMetric(90.0, 220),
        max_call_change_oi=StrikeMetric(110.0, 15),
        max_put_change_oi=StrikeMetric(90.0, 25),
        resistance_strike=110.0,
        support_strike=90.0,
        max_pain_strike=100.0,
        call_pressure=PressureType.CALL_WRITING,
        put_pressure=PressureType.PUT_WRITING,
        positioning_bias=PositioningBias.BULLISH,
        strikes=strikes,
    )


def runtime(symbol=RuntimeInstrument.NIFTY, option_chain=None):
    return RuntimeSnapshot(symbol, "1m", RuntimeStatus.CREATED, None, None, None, None, None, None, option_chain, None, None, None, None, None, None, None, NOW)


def lifecycle(*runtimes):
    orchestrator = OrchestratorSnapshot(
        RuntimeStatus.RUNNING,
        ExecutionSafetyMode.ANALYSIS_ONLY,
        BrokerExecutionMode.DRY_RUN,
        tuple(item.symbol for item in runtimes),
        True,
        False,
        runtimes,
    )
    return LifecycleSnapshot(RuntimeStatus.RUNNING, 1, 0, 0, NOW, None, None, orchestrator)


def test_no_option_chain_state_produces_unavailable_view():
    view = build_option_chain_view(runtime())
    assert view.available is False
    assert view.symbol == "NIFTY"
    assert view.strikes == ()


def test_complete_state_maps_summary_analytics_pressures_and_bias():
    source = state()
    view = build_option_chain_view(runtime(option_chain=source))
    assert view.available is True
    assert view.symbol == "NIFTY"
    assert view.exchange == "NSE"
    assert view.expiry_date == date(2026, 7, 30)
    assert view.timestamp is NOW
    assert view.underlying_price == 101.0
    assert view.atm_strike == 100.0
    assert view.strike_count == 3
    assert view.total_call_oi == 340
    assert view.total_put_oi == 420
    assert view.total_call_change_oi == 16
    assert view.total_put_change_oi == 16
    assert view.oi_pcr == 1.235
    assert view.change_oi_pcr == 1.0
    assert view.max_call_oi_strike == 110.0
    assert view.max_call_oi_value == 180
    assert view.max_put_oi_strike == 90.0
    assert view.max_put_oi_value == 220
    assert view.max_call_change_oi_strike == 110.0
    assert view.max_call_change_oi_value == 15
    assert view.max_put_change_oi_strike == 90.0
    assert view.max_put_change_oi_value == 25
    assert view.support_strike == 90.0
    assert view.resistance_strike == 110.0
    assert view.max_pain_strike == 100.0
    assert view.call_pressure == "Call Writing"
    assert view.put_pressure == "Put Writing"
    assert view.positioning_bias == "Bullish"


def test_strike_rows_are_sorted_atm_marked_missing_legs_safe_and_source_not_mutated():
    source = state(
        strikes=(
            OptionStrike(110.0, None, put(5.0, 80, -2, 15)),
            OptionStrike(90.0, call(18.0, 60, -4, 10), None),
            OptionStrike(100.0, call(), put()),
        )
    )
    original_order = tuple(strike.strike_price for strike in source.strikes)
    view = build_option_chain_view(runtime(option_chain=source))
    assert tuple(row.strike_price for row in view.strikes) == (90.0, 100.0, 110.0)
    assert [row.is_atm for row in view.strikes] == [False, True, False]
    assert view.strikes[0].put_last_price is None
    assert view.strikes[2].call_last_price is None
    assert tuple(strike.strike_price for strike in source.strikes) == original_order


def test_dashboard_tuple_alignment_and_stable_instrument_order_include_option_chain_views():
    sensex = runtime(RuntimeInstrument.SENSEX, state("SENSEX"))
    banknifty = runtime(RuntimeInstrument.BANKNIFTY, state("BANKNIFTY"))
    nifty = runtime(RuntimeInstrument.NIFTY, state("NIFTY"))
    view = build_dashboard_view(lifecycle(sensex, banknifty, nifty))
    assert tuple(market.symbol for market in view.markets) == ("NIFTY", "BANKNIFTY", "SENSEX")
    assert tuple(price_action.symbol for price_action in view.price_actions) == ("NIFTY", "BANKNIFTY", "SENSEX")
    assert tuple(chain.symbol for chain in view.option_chains) == ("NIFTY", "BANKNIFTY", "SENSEX")
    assert len(view.price_actions) == len(view.option_chains) == len(view.markets) == len(view.ai) == len(view.strategies) == len(view.positions) == len(view.journals)
