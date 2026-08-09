"""
Deterministic option-contract selection for OSE-1.
"""

from __future__ import annotations

from datetime import date

from application.enums import RuntimeInstrument
from brokers.zerodha.options.models import ZerodhaOptionUniverse
from core.enums.exchange import Exchange
from engines.option_chain.enums import OptionType
from engines.option_chain.models import OptionChainSnapshot, OptionLeg
from engines.runtime_adapter import TradeCandidate, TradeCandidateDirection, TradeCandidateState
from engines.vision_method import VisionMethodSnapshot, VisionMethodValidationReport

from .enums import OptionPaperMoneyness, OptionPaperTransactionType, OptionPaperUnderlyingDirection
from .models import DirectionalOptionSellingConfiguration, OptionTradeCandidate


def build_directional_option_trade_candidate(
    *,
    trade_candidate: TradeCandidate,
    vision_snapshot: VisionMethodSnapshot,
    validation_report: VisionMethodValidationReport,
    option_universe: ZerodhaOptionUniverse,
    option_chain_snapshot: OptionChainSnapshot,
    configuration: DirectionalOptionSellingConfiguration,
    runtime_session_id: str,
    trading_date: date,
) -> OptionTradeCandidate:
    if trade_candidate.candidate_state not in {TradeCandidateState.LONG, TradeCandidateState.SHORT}:
        raise ValueError("directional option selling requires an actionable Vision TradeCandidate")
    if trade_candidate.direction is TradeCandidateDirection.NONE:
        raise ValueError("directional option selling requires a directional underlying candidate")
    if trade_candidate.instrument.value != option_universe.underlying.value:
        raise ValueError("option universe underlying does not match trade candidate")
    if option_chain_snapshot.symbol != option_universe.underlying.value:
        raise ValueError("option chain snapshot underlying does not match option universe")
    if option_chain_snapshot.expiry_date != option_universe.expiry.expiry:
        raise ValueError("option chain snapshot expiry does not match option universe")

    option_type = OptionType.PUT if trade_candidate.direction is TradeCandidateDirection.LONG else OptionType.CALL
    underlying_direction = (
        OptionPaperUnderlyingDirection.BULLISH
        if trade_candidate.direction is TradeCandidateDirection.LONG
        else OptionPaperUnderlyingDirection.BEARISH
    )
    candidates = []
    strike_lookup = {strike.strike_price: strike for strike in option_chain_snapshot.strikes}
    for step in configuration.selectable_itm_steps:
        try:
            pair = _pair_for_step(option_universe, option_type, step)
        except ValueError:
            continue
        market_strike = strike_lookup.get(pair.strike)
        if market_strike is None:
            continue
        leg = market_strike.put if option_type is OptionType.PUT else market_strike.call
        if leg is None:
            continue
        if not _valid_leg(leg, configuration):
            continue
        contract = pair.put if option_type is OptionType.PUT else pair.call
        spread = _spread(leg)
        premium = _premium(leg)
        score = _selection_score(step, leg, spread)
        candidates.append((score, step, pair.strike, contract, leg, spread, premium))
    if not candidates:
        raise ValueError("no valid ATM/ITM option contract available for directional paper selling")

    _, step, strike, contract, leg, spread, premium = sorted(candidates, key=lambda item: (-item[0], item[1], item[2]))[0]
    moneyness = OptionPaperMoneyness.ATM if step == 0 else OptionPaperMoneyness.ITM
    exchange = Exchange.BSE if option_universe.venue.value == "BFO" else Exchange.NSE
    return OptionTradeCandidate(
        candidate_id=":".join(
            (
                "OSE1",
                trade_candidate.instrument.value,
                trade_candidate.timestamp.isoformat(),
                contract.tradingsymbol,
                str(contract.instrument_token),
            )
        ),
        runtime_session_id=runtime_session_id,
        trading_date=trading_date,
        created_at=trade_candidate.timestamp,
        underlying=trade_candidate.instrument,
        underlying_direction=underlying_direction,
        underlying_spot=option_chain_snapshot.underlying_price,
        decision_timeframe=trade_candidate.timeframe,
        source_vision_reference=trade_candidate.snapshot_reference,
        source_trade_candidate_reference=":".join((trade_candidate.instrument.value, trade_candidate.timestamp.isoformat(), trade_candidate.candidate_state.value)),
        expiry=option_universe.expiry.expiry,
        strike=strike,
        option_type=option_type,
        transaction_type=OptionPaperTransactionType.SELL,
        moneyness=moneyness,
        itm_steps=step,
        trading_symbol=contract.tradingsymbol,
        instrument_token=contract.instrument_token,
        exchange=exchange,
        premium_reference=premium,
        bid=leg.bid_price,
        ask=leg.ask_price,
        spread=spread,
        open_interest=leg.open_interest,
        volume=leg.volume,
        implied_volatility=None,
        delta=None,
        lot_size=contract.lot_size,
        underlying_invalidation=trade_candidate.stop_loss_zone,
        underlying_target_context=trade_candidate.target_zone,
        selection_score=round(float(_selection_score(step, leg, spread)), 6),
        selection_reasoning=(
            "Vision Method produced an actionable underlying candidate.",
            f"{underlying_direction.value} underlying maps to SELL {option_type.value.upper()}.",
            f"Selected {moneyness.value.upper()} contract at {strike:g} using canonical option universe.",
        ),
        status="selected",
    )


def _pair_for_step(universe: ZerodhaOptionUniverse, option_type: OptionType, step: int):
    strikes = tuple(pair.strike for pair in universe.pairs)
    atm_index = strikes.index(universe.atm_strike)
    index = atm_index - step if option_type is OptionType.PUT else atm_index + step
    if index < 0 or index >= len(universe.pairs):
        raise ValueError("requested ITM step is outside the option universe")
    return universe.pairs[index]


def _valid_leg(leg: OptionLeg, configuration: DirectionalOptionSellingConfiguration) -> bool:
    if _premium(leg) <= 0:
        return False
    if leg.open_interest < configuration.minimum_open_interest:
        return False
    if leg.volume < configuration.minimum_volume:
        return False
    spread = _spread(leg)
    if spread is not None and spread / _premium(leg) > configuration.maximum_spread_fraction:
        return False
    return True


def _premium(leg: OptionLeg) -> float:
    if leg.bid_price is not None and leg.bid_price > 0:
        return float(leg.bid_price)
    return float(leg.last_price)


def _spread(leg: OptionLeg) -> float | None:
    if leg.bid_price is None or leg.ask_price is None:
        return None
    return round(float(leg.ask_price - leg.bid_price), 6)


def _selection_score(step: int, leg: OptionLeg, spread: float | None) -> float:
    liquidity = min(float(leg.open_interest), 100000.0) / 100000.0
    volume = min(float(leg.volume), 100000.0) / 100000.0
    spread_penalty = 0.0 if spread is None else min(spread / max(_premium(leg), 1.0), 1.0)
    return 100.0 - (step * 10.0) + liquidity + volume - spread_penalty
