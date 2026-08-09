from datetime import date

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
from core.event_bus import EventBus
from engines.option_chain.enums import OptionType
from engines.option_chain.models import OptionChainSnapshot, OptionLeg, OptionStrike
from engines.option_paper_execution import (
    DirectionalOptionSellingConfiguration,
    OptionPaperExecutionStyle,
    OptionPaperPositionStatus,
    OptionPaperRiskDecision,
)
from engines.option_paper_execution.lifecycle import open_option_paper_position, update_option_paper_position
from engines.option_paper_execution.risk import evaluate_option_paper_risk
from engines.option_paper_execution.selector import build_directional_option_trade_candidate
from engines.runtime_adapter import TradeCandidateDirection
from engines.vision_method import (
    VisionBOS,
    VisionBreakDirection,
    VisionCamarillaZone,
    VisionCPRRelation,
    VisionOpeningRangeState,
    VisionRangeLocation,
    VisionStructurePattern,
    VisionStructureTrend,
    validate_vision_method,
)
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


def universe(strikes=(24900, 24950, 25000, 25050, 25100, 25150, 25200), lot_size=75):
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


def chain_snapshot(*, put_bid=100.0, call_bid=110.0):
    strikes = []
    for strike in (24900, 24950, 25000, 25050, 25100, 25150, 25200):
        call_price = call_bid + max(0, (25000 - strike) / 10)
        put_price = put_bid + max(0, (strike - 25000) / 10)
        strikes.append(
            OptionStrike(
                float(strike),
                OptionLeg(OptionType.CALL, call_price, 5000, 100, 200, call_price, call_price + 1.0),
                OptionLeg(OptionType.PUT, put_price, 5000, 100, 200, put_price, put_price + 1.0),
            )
        )
    return OptionChainSnapshot("NIFTY", "NSE", EXPIRY, NOW, 25000.0, tuple(strikes))


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
        setup_qualification_context=setup(supporting=("Below CPR", "Below L3", "Bearish BOS")),
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
    reduced = evaluate_option_paper_risk(option_trade, option_config(risk_fraction_per_trade=0.02, stop_premium_multiplier=2.2))
    rejected = evaluate_option_paper_risk(option_trade, option_config(risk_fraction_per_trade=0.0001))

    assert approved.decision is OptionPaperRiskDecision.APPROVED
    assert approved.approved_lots == 3
    assert reduced.decision is OptionPaperRiskDecision.APPROVED_REDUCED
    assert reduced.approved_lots == 1
    assert rejected.decision is OptionPaperRiskDecision.REJECTED


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
    view = item.snapshot()

    assert view.option_trade_candidate is not None
    assert view.option_trade_candidate.option_type is OptionType.PUT
    assert view.option_paper_risk.decision in {OptionPaperRiskDecision.APPROVED, OptionPaperRiskDecision.APPROVED_REDUCED}
    assert view.option_paper_position.status is OptionPaperPositionStatus.OPEN
    assert view.strategy_decision_v2 is None
    assert view.risk_management_v2 is None
    assert view.trade_lifecycle_v1.processing_count == 0
    assert view.canonical_paper_position.source == "VISION_METHOD_OPTION_SELLING_PAPER"
