from dataclasses import replace
from datetime import date, timedelta

import pytest

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaSubscriptionMode
from brokers.zerodha.options.enums import ZerodhaDerivativeVenue, ZerodhaExpiryKind, ZerodhaOptionRight
from brokers.zerodha.options.models import (
    ZerodhaExpiry,
    ZerodhaOptionContract,
    ZerodhaOptionPair,
    ZerodhaOptionUniverse,
)
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from dashboard.presenters import build_position_view
from engines.option_chain.enums import OptionType
from engines.option_chain.models import OptionChainSnapshot, OptionLeg, OptionStrike
from engines.option_paper_execution import (
    OptionContractRejectionReason,
    DirectionalOptionSellingConfiguration,
    OptionPaperExecutionStyle,
    OptionPaperPositionStatus,
    OptionPaperRiskDecision,
    OptionPaperSelectionPolicy,
)
from engines.option_paper_execution.lifecycle import open_option_paper_position, update_option_paper_position
from engines.option_paper_execution.risk import evaluate_option_paper_risk
from engines.option_paper_execution.selector import OptionContractSelectionError, build_directional_option_trade_candidate
from engines.runtime_adapter import TradeCandidateDirection, TradeCandidateState
from engines.trade_journal_v1 import TradeJournalV1Configuration, TradeJournalV1Engine, TradeRecordStatus
from engines.vision_method import (
    VisionBOS,
    VisionBreakDirection,
    VisionCamarillaZone,
    VisionCPRRelation,
    VisionOpeningRangeState,
    VisionRangeLocation,
    VisionSetupDirection,
    VisionStructurePattern,
    VisionStructureTrend,
    VisionTriggerDirection,
    VisionTriggerType,
    validate_vision_method,
)
from tests.test_vision_method_calculator_v1 import trigger
from tests.test_vision_method_validation_v1 import NOW, level, opening, setup, snapshot, structure, structure_event


EXPIRY = date(2026, 8, 27)


def option_config(**overrides):
    values = {
        "execution_style": OptionPaperExecutionStyle.DIRECTIONAL_OPTION_SELLING_PAPER,
        "paper_capital": 750000.0,
        "max_nifty_lots": 3,
        "risk_fraction_per_trade": 0.01,
        "stop_premium_multiplier": 1.5,
        "target_premium_multiplier": 0.5,
    }
    values.update(overrides)
    return DirectionalOptionSellingConfiguration(**values)


def contract(token, strike, right, lot_size=75):
    return ZerodhaOptionContract(
        instrument_token=token,
        exchange_token=token + 10000,
        underlying=__import__("core.enums.instrument", fromlist=["Instrument"]).Instrument.NIFTY,
        venue=ZerodhaDerivativeVenue.NFO,
        segment="NFO-OPT",
        tradingsymbol=f"NIFTY26827{int(strike)}{right.value}",
        name="NIFTY",
        expiry=EXPIRY,
        strike=float(strike),
        right=right,
        lot_size=lot_size,
        tick_size=0.05,
    )


def universe(strikes=(24850, 24900, 24950, 25000, 25050, 25100, 25150, 25200), lot_size=75):
    instrument = __import__("core.enums.instrument", fromlist=["Instrument"]).Instrument.NIFTY
    expiry = ZerodhaExpiry(instrument, EXPIRY, ZerodhaExpiryKind.WEEKLY, len(strikes) * 2, len(strikes), strikes[0], strikes[-1])
    pairs = []
    subscriptions = []
    token = 1000
    for strike in strikes:
        call = contract(token, strike, ZerodhaOptionRight.CALL, lot_size)
        put = contract(token + 1, strike, ZerodhaOptionRight.PUT, lot_size)
        pair = ZerodhaOptionPair(instrument, expiry, float(strike), call, put)
        pairs.append(pair)
        subscriptions.extend(
            (
                ZerodhaInstrumentSubscription(call.instrument_token, instrument, Exchange.NSE, ZerodhaSubscriptionMode.FULL),
                ZerodhaInstrumentSubscription(put.instrument_token, instrument, Exchange.NSE, ZerodhaSubscriptionMode.FULL),
            )
        )
        token += 2
    return ZerodhaOptionUniverse(
        instrument,
        ZerodhaDerivativeVenue.NFO,
        expiry,
        25000.0,
        25000.0,
        50.0,
        tuple(pairs),
        tuple(subscriptions),
        NOW,
    )


def chain_snapshot(
    *,
    strikes=(24850, 24900, 24950, 25000, 25050, 25100, 25150, 25200),
    put_bid=100.0,
    call_bid=110.0,
    timestamp=NOW,
    expiry=EXPIRY,
    invalid_put_strikes=(),
    invalid_call_strikes=(),
):
    rows = []
    for strike in strikes:
        call_price = call_bid + max(0, (25000 - strike) / 10)
        put_price = put_bid + max(0, (strike - 25000) / 10)
        call_oi = put_oi = 5000
        call_volume = put_volume = 200
        if strike in invalid_call_strikes:
            call_price = 0.0
            call_oi = 0
            call_volume = 0
        if strike in invalid_put_strikes:
            put_price = 0.0
            put_oi = 0
            put_volume = 0
        rows.append(
            OptionStrike(
                float(strike),
                OptionLeg(OptionType.CALL, call_price, call_oi, 100, call_volume, call_price if call_price else None, call_price + 1.0 if call_price else None),
                OptionLeg(OptionType.PUT, put_price, put_oi, 100, put_volume, put_price if put_price else None, put_price + 1.0 if put_price else None),
            )
        )
    return OptionChainSnapshot("NIFTY", "NSE", expiry, timestamp, 25000.0, tuple(rows))


def chain_with_put_quotes(quotes, *, timestamp=NOW):
    rows = []
    for strike, attrs in quotes.items():
        bid = attrs.get("bid", attrs.get("last", 100.0))
        ask = attrs.get("ask", bid + 1.0 if bid > 0 else None)
        last = attrs.get("last", bid)
        rows.append(
            OptionStrike(
                float(strike),
                OptionLeg(OptionType.CALL, 110.0, 5000, 100, 200, 110.0, 111.0),
                OptionLeg(
                    OptionType.PUT,
                    float(last),
                    int(attrs.get("oi", 5000)),
                    100,
                    int(attrs.get("volume", 200)),
                    None if bid is None else float(bid),
                    None if ask is None else float(ask),
                ),
            )
        )
    return OptionChainSnapshot("NIFTY", "NSE", EXPIRY, timestamp, 25000.0, tuple(rows))


def bearish_snapshot():
    return snapshot(
        level_context=level(cpr=VisionCPRRelation.BELOW_CPR, zone=VisionCamarillaZone.L3_L4),
        opening_range_context=opening(
            state=VisionOpeningRangeState.BREAK_BELOW,
            direction=VisionBreakDirection.DOWN,
            location=VisionRangeLocation.BELOW_RANGE,
        ),
        structure_context=structure(trend=VisionStructureTrend.BEARISH, pattern=VisionStructurePattern.LL),
        structure_event_context=structure_event(bos=VisionBOS.BEARISH_BOS),
        setup_qualification_context=setup(
            supporting=("Below CPR", "Below L3", "Bearish BOS"),
            setup_direction=VisionSetupDirection.BEARISH,
        ),
        price_action_trigger_context=trigger(
            direction=VisionTriggerDirection.BEARISH,
            trigger_type=VisionTriggerType.BEARISH_INITIATIVE_BREAKOUT,
        ),
    )


def test_bullish_vision_candidate_selects_atm_put_for_paper_sell():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)

    option_trade = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(),
        option_chain_snapshot=chain_snapshot(),
        configuration=option_config(),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )

    assert trade.direction is TradeCandidateDirection.LONG
    assert option_trade.transaction_type.value == "sell"
    assert option_trade.option_type is OptionType.PUT
    assert option_trade.strike == 25000.0
    assert option_trade.moneyness.value == "atm"
    assert option_trade.lot_size == 75


def test_bearish_vision_candidate_selects_atm_call_for_paper_sell():
    method = bearish_snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)

    option_trade = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(),
        option_chain_snapshot=chain_snapshot(),
        configuration=option_config(),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )

    assert trade.direction is TradeCandidateDirection.SHORT
    assert option_trade.option_type is OptionType.CALL
    assert option_trade.strike == 25000.0


def test_option_risk_can_approve_reduce_or_reject_lots():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)
    option_trade = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(),
        option_chain_snapshot=chain_snapshot(put_bid=100.0),
        configuration=option_config(),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )

    approved = evaluate_option_paper_risk(option_trade, option_config(risk_fraction_per_trade=0.02))
    reduced_two = evaluate_option_paper_risk(option_trade, option_config(risk_fraction_per_trade=0.01))
    reduced_one = evaluate_option_paper_risk(option_trade, option_config(risk_fraction_per_trade=0.0054))
    rejected = evaluate_option_paper_risk(option_trade, option_config(risk_fraction_per_trade=0.0001))

    assert approved.decision is OptionPaperRiskDecision.APPROVED
    assert approved.approved_lots == 3
    assert reduced_two.decision is OptionPaperRiskDecision.APPROVED_REDUCED
    assert reduced_two.approved_lots == 2
    assert reduced_one.decision is OptionPaperRiskDecision.APPROVED_REDUCED
    assert reduced_one.approved_lots == 1
    assert rejected.decision is OptionPaperRiskDecision.REJECTED
    assert approved.approved_quantity == approved.approved_lots * option_trade.lot_size
    assert approved.risk_per_unit == approved.stop_premium - approved.entry_premium
    assert approved.reward_per_unit == approved.entry_premium - approved.target_premium
    assert approved.planned_rupee_risk == approved.risk_per_unit * approved.approved_quantity


def test_short_option_mtm_profit_on_premium_decay_and_loss_on_stop():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)
    option_trade = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(),
        option_chain_snapshot=chain_snapshot(put_bid=100.0),
        configuration=option_config(),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )
    risk = evaluate_option_paper_risk(option_trade, option_config())
    opened = open_option_paper_position(risk)

    target = update_option_paper_position(opened, current_premium=49.0, underlying_price=25050.0, timestamp=NOW)
    stopped = update_option_paper_position(opened, current_premium=151.0, underlying_price=25050.0, timestamp=NOW)

    assert target.status is OptionPaperPositionStatus.TARGET_HIT
    assert target.realized_pnl > 0
    assert stopped.status is OptionPaperPositionStatus.STOP_HIT
    assert stopped.realized_pnl < 0


def test_bullish_put_itm_depth_moves_above_atm_without_hardcoded_interval():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)

    one_step = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(strikes=(24700, 24800, 24900, 25000, 25100, 25200, 25300)),
        option_chain_snapshot=chain_snapshot(strikes=(24700, 24800, 24900, 25000, 25100, 25200, 25300), invalid_put_strikes=(25000,)),
        configuration=option_config(),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )
    two_step = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(strikes=(24700, 24800, 24900, 25000, 25100, 25200, 25300)),
        option_chain_snapshot=chain_snapshot(strikes=(24700, 24800, 24900, 25000, 25100, 25200, 25300), invalid_put_strikes=(25000, 25100)),
        configuration=option_config(),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )
    three_step = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(strikes=(24700, 24800, 24900, 25000, 25100, 25200, 25300)),
        option_chain_snapshot=chain_snapshot(strikes=(24700, 24800, 24900, 25000, 25100, 25200, 25300), invalid_put_strikes=(25000, 25100, 25200)),
        configuration=option_config(),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )

    assert one_step.itm_steps == 1
    assert one_step.strike == 25100.0
    assert two_step.itm_steps == 2
    assert two_step.strike == 25200.0
    assert three_step.itm_steps == 3
    assert three_step.strike == 25300.0


def test_bearish_call_itm_depth_moves_below_atm():
    method = bearish_snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)

    option_trade = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(strikes=(24700, 24800, 24900, 25000, 25100, 25200, 25300)),
        option_chain_snapshot=chain_snapshot(strikes=(24700, 24800, 24900, 25000, 25100, 25200, 25300), invalid_call_strikes=(25000,)),
        configuration=option_config(),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )

    assert option_trade.option_type is OptionType.CALL
    assert option_trade.itm_steps == 1
    assert option_trade.strike == 24900.0


def test_preferred_itm_policy_can_select_itm_while_atm_is_valid():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)

    option_trade = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(strikes=(24900, 25000, 25100, 25200)),
        option_chain_snapshot=chain_snapshot(strikes=(24900, 25000, 25100, 25200)),
        configuration=option_config(
            selection_policy=OptionPaperSelectionPolicy.PREFERRED_ITM_DEPTH,
            preferred_itm_step=1,
        ),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )

    assert option_trade.strike == 25100.0
    assert option_trade.itm_steps == 1
    assert option_trade.moneyness.value == "itm"
    assert "preferred_itm_depth" in " ".join(option_trade.selection_reasoning)


def test_best_liquid_policy_can_select_deeper_itm_on_quote_quality():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)

    option_trade = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(strikes=(24900, 25000, 25100, 25200)),
        option_chain_snapshot=chain_with_put_quotes(
            {
                25000: {"bid": 100.0, "ask": 114.0, "oi": 10, "volume": 1},
                25100: {"bid": 110.0, "ask": 111.0, "oi": 90000, "volume": 90000},
                25200: {"bid": 120.0, "ask": 121.0, "oi": 50000, "volume": 50000},
            }
        ),
        configuration=option_config(selection_policy=OptionPaperSelectionPolicy.BEST_LIQUID_VALID),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )

    assert option_trade.strike == 25100.0
    assert option_trade.itm_steps == 1
    assert option_trade.selection_policy is OptionPaperSelectionPolicy.BEST_LIQUID_VALID
    assert any(item.strike == 25000.0 for item in option_trade.selection_diagnostics)
    assert any("deterministic liquidity score" in reason for reason in option_trade.selection_reasoning)


def test_best_liquid_policy_uses_depth_only_as_tie_break():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)

    option_trade = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(strikes=(24900, 25000, 25100)),
        option_chain_snapshot=chain_with_put_quotes(
            {
                25000: {"bid": 100.0, "ask": 101.0, "oi": 5000, "volume": 200},
                25100: {"bid": 100.0, "ask": 101.0, "oi": 5000, "volume": 200},
            }
        ),
        configuration=option_config(selection_policy=OptionPaperSelectionPolicy.BEST_LIQUID_VALID),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )

    assert option_trade.strike == 25000.0
    assert option_trade.itm_steps == 0


def test_prepare_candidates_stale_expired_and_cross_session_option_data_are_rejected():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)
    prepare = replace(trade, candidate_state=TradeCandidateState.WAITING_LONG)

    with pytest.raises(ValueError, match="actionable"):
        build_directional_option_trade_candidate(
            trade_candidate=prepare,
            vision_snapshot=method,
            validation_report=report,
            option_universe=universe(),
            option_chain_snapshot=chain_snapshot(),
            configuration=option_config(),
            runtime_session_id="NIFTY:2026-08-03",
            trading_date=NOW.date(),
        )
    with pytest.raises(ValueError, match="expired"):
        build_directional_option_trade_candidate(
            trade_candidate=trade,
            vision_snapshot=method,
            validation_report=report,
            option_universe=universe(),
            option_chain_snapshot=chain_snapshot(),
            configuration=option_config(),
            runtime_session_id="NIFTY:2026-08-03",
            trading_date=date(2026, 8, 28),
        )
    with pytest.raises(ValueError, match="stale"):
        build_directional_option_trade_candidate(
            trade_candidate=trade,
            vision_snapshot=method,
            validation_report=report,
            option_universe=universe(),
            option_chain_snapshot=chain_snapshot(timestamp=NOW - timedelta(minutes=10)),
            configuration=option_config(maximum_quote_age_seconds=60.0),
            runtime_session_id="NIFTY:2026-08-03",
            trading_date=NOW.date(),
        )
    with pytest.raises(ValueError, match="trading session"):
        build_directional_option_trade_candidate(
            trade_candidate=trade,
            vision_snapshot=method,
            validation_report=report,
            option_universe=universe(),
            option_chain_snapshot=chain_snapshot(timestamp=NOW - timedelta(days=1)),
            configuration=option_config(maximum_quote_age_seconds=999999.0),
            runtime_session_id="NIFTY:2026-08-03",
            trading_date=NOW.date(),
        )


def test_future_option_quote_is_rejected_with_typed_stage():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)

    with pytest.raises(OptionContractSelectionError) as future:
        build_directional_option_trade_candidate(
            trade_candidate=trade,
            vision_snapshot=method,
            validation_report=report,
            option_universe=universe(),
            option_chain_snapshot=chain_snapshot(timestamp=NOW + timedelta(seconds=2)),
            configuration=option_config(),
            runtime_session_id="NIFTY:2026-08-03",
            trading_date=NOW.date(),
        )

    assert future.value.stage == "OPTION_CHAIN_FUTURE"


def test_stale_option_quote_is_rejected_without_absolute_age():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)

    with pytest.raises(OptionContractSelectionError) as stale:
        build_directional_option_trade_candidate(
            trade_candidate=trade,
            vision_snapshot=method,
            validation_report=report,
            option_universe=universe(),
            option_chain_snapshot=chain_snapshot(timestamp=NOW - timedelta(seconds=61)),
            configuration=option_config(maximum_quote_age_seconds=60.0),
            runtime_session_id="NIFTY:2026-08-03",
            trading_date=NOW.date(),
        )

    assert stale.value.stage == "OPTION_CHAIN_STALE"


def test_naive_option_quote_timestamp_is_rejected_with_typed_stage():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)

    with pytest.raises(OptionContractSelectionError) as naive:
        build_directional_option_trade_candidate(
            trade_candidate=trade,
            vision_snapshot=method,
            validation_report=report,
            option_universe=universe(),
            option_chain_snapshot=chain_snapshot(timestamp=NOW.replace(tzinfo=None)),
            configuration=option_config(),
            runtime_session_id="NIFTY:2026-08-03",
            trading_date=NOW.date(),
        )

    assert naive.value.stage == "OPTION_CHAIN_TIMEZONE_MISMATCH"


def test_no_valid_contract_returns_per_strike_diagnostics():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)

    with pytest.raises(OptionContractSelectionError) as no_valid:
        build_directional_option_trade_candidate(
            trade_candidate=trade,
            vision_snapshot=method,
            validation_report=report,
            option_universe=universe(strikes=(24900, 25000, 25100)),
            option_chain_snapshot=chain_with_put_quotes(
                {
                    25000: {"bid": 0.0, "ask": None, "last": 0.0, "oi": 0, "volume": 0},
                    25100: {"bid": 100.0, "ask": 130.0, "oi": 10, "volume": 0},
                }
            ),
            configuration=option_config(minimum_open_interest=100, minimum_volume=100, maximum_spread_fraction=0.05),
            runtime_session_id="NIFTY:2026-08-03",
            trading_date=NOW.date(),
        )

    diagnostics = no_valid.value.diagnostics
    assert no_valid.value.stage == "NO_VALID_ATM_ITM_CONTRACT"
    assert len(diagnostics) == 4
    by_strike = {item.strike: item for item in diagnostics if item.strike is not None}
    assert OptionContractRejectionReason.INVALID_PREMIUM in by_strike[25000.0].rejection_reasons
    assert OptionContractRejectionReason.OI_BELOW_MINIMUM in by_strike[25000.0].rejection_reasons
    assert OptionContractRejectionReason.VOLUME_BELOW_MINIMUM in by_strike[25100.0].rejection_reasons
    assert OptionContractRejectionReason.SPREAD_TOO_WIDE in by_strike[25100.0].rejection_reasons
    assert any(OptionContractRejectionReason.OUTSIDE_UNIVERSE in item.rejection_reasons for item in diagnostics)


def test_underlying_invalidation_closes_and_closed_position_is_not_updated_twice():
    method = snapshot()
    report = validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)
    option_trade = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(),
        option_chain_snapshot=chain_snapshot(put_bid=100.0),
        configuration=option_config(),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )
    option_trade = replace(option_trade, underlying_invalidation="Below 24900")
    opened = open_option_paper_position(evaluate_option_paper_risk(option_trade, option_config()))

    closed = update_option_paper_position(opened, current_premium=101.0, underlying_price=24899.0, timestamp=NOW)
    second = update_option_paper_position(closed, current_premium=140.0, underlying_price=24800.0, timestamp=NOW + timedelta(minutes=1))

    assert closed.status is OptionPaperPositionStatus.INVALIDATED
    assert closed.closed_at == NOW
    assert second is closed


def test_symbol_runtime_directional_option_selling_stays_paper_only_and_has_no_strategy_handoff():
    item = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(option_expiry_date=EXPIRY, directional_option_selling_configuration=option_config()),
        RuntimeInstrument.NIFTY,
    )
    item.start()
    item._last_tick = __import__("tests.test_vision_paper_trading_integration_v1", fromlist=["tick"]).tick()
    item.set_option_universe(universe())
    item.process_option_chain(chain_snapshot())

    method = snapshot()
    report = validate_vision_method(method)
    item.process_vision_method_paper_trade(method, report)
    item.process_vision_method_paper_trade(method, report)
    view = item.snapshot()

    assert view.option_trade_candidate is not None
    assert view.option_trade_candidate.option_type is OptionType.PUT
    assert view.option_paper_risk.decision in {OptionPaperRiskDecision.APPROVED, OptionPaperRiskDecision.APPROVED_REDUCED}
    assert view.option_paper_position.status is OptionPaperPositionStatus.OPEN
    assert view.strategy_decision_v2 is None
    assert view.risk_management_v2 is None
    assert view.trade_lifecycle_v1.processing_count == 0
    assert view.canonical_paper_position.source == "VISION_METHOD_OPTION_SELLING_PAPER"
    assert view.option_paper_position.position_id == view.canonical_paper_position.trade_id
    assert build_position_view(view).status == "Paper Option Position Open"
    assert build_position_view(view).last_price == view.option_paper_position.current_premium


def test_symbol_runtime_exposes_option_selection_rejection_diagnostics():
    item = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(
            option_expiry_date=EXPIRY,
            directional_option_selling_configuration=option_config(
                minimum_open_interest=100,
                minimum_volume=100,
                maximum_spread_fraction=0.05,
            ),
        ),
        RuntimeInstrument.NIFTY,
    )
    item.start()
    item._last_tick = __import__("tests.test_vision_paper_trading_integration_v1", fromlist=["tick"]).tick()
    item.set_option_universe(universe(strikes=(24900, 25000, 25100)))
    item.process_option_chain(
        chain_with_put_quotes(
            {
                25000: {"bid": 0.0, "ask": None, "last": 0.0, "oi": 0, "volume": 0},
                25100: {"bid": 100.0, "ask": 130.0, "oi": 10, "volume": 0},
            }
        )
    )

    method = snapshot()
    report = validate_vision_method(method)
    item.process_vision_method_paper_trade(method, report)
    view = item.snapshot()

    assert view.option_trade_candidate is None
    assert view.option_paper_position is None
    assert view.decision_audit.rejected_at == "NO_VALID_ATM_ITM_CONTRACT"
    assert view.option_selection_diagnostics
    assert any(OptionContractRejectionReason.SPREAD_TOO_WIDE in item.rejection_reasons for item in view.option_selection_diagnostics)


def test_symbol_runtime_marks_open_short_option_position_with_buy_to_close_ask():
    item = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(option_expiry_date=EXPIRY, directional_option_selling_configuration=option_config()),
        RuntimeInstrument.NIFTY,
    )
    item.start()
    runtime_tick = __import__("tests.test_vision_paper_trading_integration_v1", fromlist=["tick"]).tick
    item.process_tick(runtime_tick())
    item.set_option_universe(universe())
    item.process_option_chain_runtime(chain_snapshot(put_bid=100.0))

    method = snapshot()
    report = validate_vision_method(method)
    item.process_vision_method_paper_trade(method, report)
    item.process_tick(runtime_tick(timestamp=NOW + timedelta(minutes=1)))
    item.process_option_chain_runtime(chain_snapshot(put_bid=49.0, timestamp=NOW + timedelta(minutes=1)))
    view = item.snapshot()

    assert view.option_paper_position is not None
    assert view.option_paper_position.current_premium == 50.0


def test_symbol_runtime_accepts_small_option_mark_lead_without_runtime_contract_failure():
    item = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(
            timeframes=("1m", "5m", "15m"),
            option_expiry_date=EXPIRY,
            directional_option_selling_configuration=option_config(),
        ),
        RuntimeInstrument.NIFTY,
    )
    item.start()
    runtime_tick = __import__("tests.test_vision_paper_trading_integration_v1", fromlist=["tick"]).tick
    item.process_tick(runtime_tick())
    item.set_option_universe(universe())
    item.process_option_chain_runtime(chain_snapshot(put_bid=100.0))

    method = snapshot()
    report = validate_vision_method(method)
    item.process_vision_method_paper_trade(method, report)
    item.process_option_chain_runtime(chain_snapshot(put_bid=80.0, timestamp=NOW + timedelta(milliseconds=175)))
    view = item.snapshot()

    assert view.runtime_session.market_timestamp == NOW
    assert view.option_paper_position.updated_at == NOW + timedelta(milliseconds=175)
    assert view.canonical_paper_position.updated_at == NOW + timedelta(milliseconds=175)
    assert view.runtime_contract_report.valid is True


def test_symbol_runtime_rejects_excessive_future_option_mark_without_advancing_clock_or_position():
    item = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(
            timeframes=("1m", "5m", "15m"),
            option_expiry_date=EXPIRY,
            directional_option_selling_configuration=option_config(),
        ),
        RuntimeInstrument.NIFTY,
    )
    item.start()
    runtime_tick = __import__("tests.test_vision_paper_trading_integration_v1", fromlist=["tick"]).tick
    item.process_tick(runtime_tick())
    item.set_option_universe(universe())
    item.process_option_chain_runtime(chain_snapshot(put_bid=100.0))

    method = snapshot()
    report = validate_vision_method(method)
    item.process_vision_method_paper_trade(method, report)
    before = item.snapshot().option_paper_position

    try:
        item.process_option_chain_runtime(chain_snapshot(put_bid=80.0, timestamp=NOW + timedelta(seconds=2)))
    except ValueError as exc:
        assert "future" in str(exc)
    else:
        raise AssertionError("future option mark beyond tolerance must be rejected")
    after = item.snapshot()

    assert after.runtime_session.market_timestamp == NOW
    assert after.option_paper_position == before
    assert after.runtime_contract_report.valid is True


def test_symbol_runtime_blocks_fresh_vision_option_paper_candidate_after_market_close():
    item = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(option_expiry_date=EXPIRY, directional_option_selling_configuration=option_config()),
        RuntimeInstrument.NIFTY,
    )
    item.start()

    post_market = NOW.replace(hour=16, minute=0)
    method = snapshot(timestamp=post_market, price_action_trigger_context=trigger(timestamp=post_market))
    report = validate_vision_method(method)
    candidate = item.process_vision_method_paper_trade(method, report)
    view = item.snapshot()

    assert candidate.candidate_state is TradeCandidateState.LONG
    assert view.vision_trade_candidate is candidate
    assert view.option_trade_candidate is None
    assert view.option_paper_risk is None
    assert view.option_paper_position is None
    assert view.decision_audit.rejected_at == "MARKET_CLOSED"
    assert "outside live session" in view.decision_audit.reason


def _option_position_for_journal(*, method=None, report=None, bearish=False):
    method = method or (bearish_snapshot() if bearish else snapshot())
    report = report or validate_vision_method(method)
    trade = __import__("engines.runtime_adapter", fromlist=["adapt_vision_method_to_trade_candidate"]).adapt_vision_method_to_trade_candidate(method, report)
    option_trade = build_directional_option_trade_candidate(
        trade_candidate=trade,
        vision_snapshot=method,
        validation_report=report,
        option_universe=universe(),
        option_chain_snapshot=chain_snapshot(call_bid=110.0, put_bid=100.0),
        configuration=option_config(),
        runtime_session_id="NIFTY:2026-08-03",
        trading_date=NOW.date(),
    )
    return open_option_paper_position(evaluate_option_paper_risk(option_trade, option_config()))


def _journal_engine(tmp_path):
    engine = TradeJournalV1Engine(
        configuration=TradeJournalV1Configuration(
            journal_path=tmp_path / "journal.jsonl",
            checkpoint_path=tmp_path / "checkpoint.json",
        )
    )
    engine.start()
    return engine


def test_option_paper_journal_open_and_premium_target_close_finalize_same_trade_once(tmp_path):
    engine = _journal_engine(tmp_path)
    opened = _option_position_for_journal()

    opened_result = engine.record_option_paper_position(opened)
    assert opened_result.status is TradeRecordStatus.RECORDED
    assert opened_result.entry.record_state == "open"
    assert engine.snapshot().trade_count == 1
    assert engine.analytics_snapshot().overall.trade_count == 0
    assert engine.durable_records() == ()

    closed = update_option_paper_position(opened, current_premium=49.0, underlying_price=25050.0, timestamp=NOW + timedelta(minutes=1))
    closed_result = engine.record_option_paper_position(closed)
    duplicate = engine.record_option_paper_position(closed)

    assert closed_result.status is TradeRecordStatus.RECORDED
    assert closed_result.entry.trade_id == opened.position_id
    assert closed_result.entry.record_state == "closed"
    assert duplicate.status is TradeRecordStatus.DUPLICATE
    assert len(engine.entries()) == 1
    assert engine.analytics_snapshot().overall.trade_count == 1
    assert engine.analytics_snapshot().overall.total_pnl == closed.realized_pnl
    records = engine.durable_records()
    assert len(records) == 1
    record = records[0]
    assert record.trade_id == opened.position_id
    assert record.option_position_reference == opened.position_id
    assert record.option_candidate_reference == opened.candidate.candidate_id
    assert record.trade_candidate_reference == opened.candidate.source_trade_candidate_reference
    assert record.vision_method_snapshot_reference == opened.candidate.source_vision_reference
    assert record.contract_trading_symbol == opened.candidate.trading_symbol
    assert record.instrument_token == opened.candidate.instrument_token
    assert record.expiry == opened.candidate.expiry
    assert record.strike == opened.candidate.strike
    assert record.option_type == opened.candidate.option_type.value
    assert record.transaction_type == "sell"
    assert record.quantity == opened.quantity
    assert record.lots == opened.lots
    assert record.lot_size == opened.candidate.lot_size
    assert record.gross_pnl == closed.realized_pnl
    assert record.net_pnl == closed.realized_pnl
    assert record.fees == 0.0
    assert record.slippage == 0.0


def test_option_paper_journal_stop_invalidation_and_simultaneous_exit_close_once(tmp_path):
    engine = _journal_engine(tmp_path)

    def cloned_position(label, *, invalidation=None):
        base = _option_position_for_journal()
        candidate = replace(
            base.candidate,
            candidate_id=f"{base.candidate.candidate_id}:{label}",
            underlying_invalidation=invalidation or base.candidate.underlying_invalidation,
        )
        risk = replace(base.risk, candidate=candidate)
        return replace(base, position_id=f"OSE1-PAPER:{candidate.candidate_id}", candidate=candidate, risk=risk)

    stopped_open = cloned_position("stop")
    invalidated_open = cloned_position("invalidation", invalidation="Below 24900")
    simultaneous_open = cloned_position("simultaneous", invalidation="Below 24900")

    stopped = update_option_paper_position(stopped_open, current_premium=151.0, underlying_price=25000.0, timestamp=NOW + timedelta(minutes=1))
    invalidated = update_option_paper_position(invalidated_open, current_premium=100.0, underlying_price=24899.0, timestamp=NOW + timedelta(minutes=2))
    simultaneous = update_option_paper_position(simultaneous_open, current_premium=49.0, underlying_price=24899.0, timestamp=NOW + timedelta(minutes=3))

    for item in (stopped, invalidated, simultaneous):
        engine.record_option_paper_position(open_option_paper_position(item.risk))
        first = engine.record_option_paper_position(item)
        second = engine.record_option_paper_position(item)
        assert first.status is TradeRecordStatus.RECORDED
        assert second.status is TradeRecordStatus.DUPLICATE

    assert len(engine.entries()) == 3
    assert len(engine.durable_records()) == 3
    assert engine.analytics_snapshot().overall.trade_count == 3


def test_option_paper_journal_previous_session_remains_historical(tmp_path):
    engine = _journal_engine(tmp_path)
    current = _option_position_for_journal()
    old_candidate = replace(current.candidate, trading_date=NOW.date() - timedelta(days=1), candidate_id=current.candidate.candidate_id + ":old")
    old_risk = replace(current.risk, candidate=old_candidate)
    old_opened_at = current.opened_at - timedelta(days=1)
    old = replace(
        current,
        position_id=current.position_id + ":old",
        candidate=old_candidate,
        risk=old_risk,
        opened_at=old_opened_at,
        updated_at=old_opened_at,
    )

    current_closed = update_option_paper_position(current, current_premium=49.0, underlying_price=25050.0, timestamp=NOW + timedelta(minutes=1))
    old_closed = update_option_paper_position(old, current_premium=49.0, underlying_price=25050.0, timestamp=NOW - timedelta(days=1))
    engine.record_option_paper_position(old_closed)
    engine.record_option_paper_position(current_closed)

    assert len(engine.durable_records(trading_date=NOW.date() - timedelta(days=1))) == 1
    assert len(engine.durable_records(trading_date=NOW.date())) == 1
    assert len(engine.durable_records()) == 2


def test_old_historical_trade_journal_records_remain_backward_compatible():
    from engines.trade_journal_v1.models import VisionTradeJournalRecord
    from engines.position_management_v1.enums import PositionExitReason
    from engines.trade_journal_v1.enums import TradeOutcome
    from core.enums.instrument import Instrument

    record = VisionTradeJournalRecord(
        trade_id="legacy",
        instrument=Instrument.NIFTY,
        exchange="NSE",
        timeframe="1m",
        trading_date=NOW.date(),
        trade_source="VISION_METHOD",
        setup_classification="trend_continuation",
        candidate_direction="long",
        candidate_quality="high",
        validation_result="valid",
        outcome=TradeOutcome.WIN,
        exit_reason=PositionExitReason.OBJECTIVE,
        vision_method_snapshot_reference="vision",
        vision_method_validation_reference="validation",
        trade_candidate_reference="candidate",
        risk_reference="risk",
        lifecycle_reference="lifecycle",
        paper_position_reference="position",
        validation_trace_reference="trace",
        entry_timestamp=NOW,
        entry_price=100.0,
        quantity=75,
        stop_price=90.0,
        target_price=120.0,
        exit_timestamp=NOW + timedelta(minutes=1),
        exit_price=120.0,
        gross_pnl=100.0,
        fees=0.0,
        slippage=0.0,
        net_pnl=100.0,
        supporting_reasons=("legacy",),
        blocking_reasons=(),
        created_at=NOW,
        updated_at=NOW,
    )

    assert record.instrument_type == "UNDERLYING"
    assert record.option_candidate_reference is None


def test_symbol_runtime_option_paper_close_is_journaled_and_forensic_linked(tmp_path):
    item = SymbolRuntime(
        EventBus(),
        configuration=RuntimeConfiguration(
            option_expiry_date=EXPIRY,
            directional_option_selling_configuration=option_config(),
        ),
        instrument=RuntimeInstrument.NIFTY,
    )
    item.trade_journal_v1_engine = _journal_engine(tmp_path)
    item.start()
    runtime_tick = __import__("tests.test_vision_paper_trading_integration_v1", fromlist=["tick"]).tick
    item.process_tick(runtime_tick())
    item.set_option_universe(universe())
    item.process_option_chain_runtime(chain_snapshot(put_bid=100.0))
    method = snapshot()
    report = validate_vision_method(method)

    item.process_vision_method_paper_trade(method, report)
    item.process_tick(runtime_tick(timestamp=NOW + timedelta(minutes=1)))
    item.process_option_chain_runtime(chain_snapshot(put_bid=49.0, timestamp=NOW + timedelta(minutes=1)))
    item.process_tick(runtime_tick(timestamp=NOW + timedelta(minutes=2)))
    item.process_option_chain_runtime(chain_snapshot(put_bid=48.0, timestamp=NOW + timedelta(minutes=2)))
    view = item.snapshot()
    records = item.trade_journal_v1_engine.durable_records()

    assert view.option_paper_position.status is OptionPaperPositionStatus.TARGET_HIT
    assert len(records) == 1
    assert records[0].option_position_reference == view.option_paper_position.position_id
    assert records[0].option_candidate_reference == view.option_trade_candidate.candidate_id
    assert records[0].trade_candidate_reference == view.option_trade_candidate.source_trade_candidate_reference
    assert records[0].vision_method_snapshot_reference == view.option_trade_candidate.source_vision_reference
    assert records[0].gross_pnl == view.option_paper_position.realized_pnl
    assert view.trade_journal_v1.analytics.overall.trade_count == 1
