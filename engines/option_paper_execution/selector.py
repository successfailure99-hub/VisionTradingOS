"""
Deterministic option-contract selection for OSE-1.
"""

from __future__ import annotations

from datetime import date, timedelta

from application.enums import RuntimeInstrument
from brokers.zerodha.options.models import ZerodhaOptionUniverse
from core.enums.exchange import Exchange
from engines.option_chain.enums import OptionType
from engines.option_chain.models import OptionChainSnapshot, OptionLeg
from engines.runtime_adapter import TradeCandidate, TradeCandidateDirection, TradeCandidateState
from engines.vision_method import VisionMethodSnapshot, VisionMethodValidationReport

from .enums import (
    OptionContractRejectionReason,
    OptionContractSelectionStatus,
    OptionPaperMoneyness,
    OptionPaperSelectionPolicy,
    OptionPaperTransactionType,
    OptionPaperUnderlyingDirection,
)
from .models import DirectionalOptionSellingConfiguration, OptionContractSelectionDiagnostic, OptionTradeCandidate


_FUTURE_QUOTE_TOLERANCE = timedelta(seconds=1)


class OptionContractSelectionError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        stage: str = "NO_VALID_ATM_ITM_CONTRACT",
        diagnostics: tuple[OptionContractSelectionDiagnostic, ...] = (),
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.diagnostics = tuple(diagnostics)


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
        raise OptionContractSelectionError("option chain snapshot expiry does not match option universe", stage="OPTION_EXPIRY_MISMATCH")
    if option_chain_snapshot.expiry_date < trading_date:
        raise OptionContractSelectionError("expired option contract cannot be selected", stage="OPTION_EXPIRY_MISMATCH")
    _validate_quote_timestamp(trade_candidate.timestamp, option_chain_snapshot.timestamp, trading_date, configuration)

    option_type = OptionType.PUT if trade_candidate.direction is TradeCandidateDirection.LONG else OptionType.CALL
    underlying_direction = (
        OptionPaperUnderlyingDirection.BULLISH
        if trade_candidate.direction is TradeCandidateDirection.LONG
        else OptionPaperUnderlyingDirection.BEARISH
    )
    candidates = []
    diagnostics: list[OptionContractSelectionDiagnostic] = []
    strike_lookup = {strike.strike_price: strike for strike in option_chain_snapshot.strikes}
    for step in configuration.selectable_itm_steps:
        try:
            pair = _pair_for_step(option_universe, option_type, step)
        except ValueError:
            diagnostics.append(_diagnostic(None, option_type, step, None, (OptionContractRejectionReason.OUTSIDE_UNIVERSE,)))
            continue
        market_strike = strike_lookup.get(pair.strike)
        if market_strike is None:
            diagnostics.append(_diagnostic(pair.strike, option_type, step, None, (OptionContractRejectionReason.MISSING_MARKET_STRIKE,)))
            continue
        leg = market_strike.put if option_type is OptionType.PUT else market_strike.call
        if leg is None:
            diagnostics.append(_diagnostic(pair.strike, option_type, step, None, (OptionContractRejectionReason.MISSING_OPTION_LEG,)))
            continue
        rejection_reasons = _leg_rejection_reasons(leg, configuration)
        diagnostics.append(_diagnostic(pair.strike, option_type, step, leg, rejection_reasons))
        if rejection_reasons != (OptionContractRejectionReason.VALID,):
            continue
        contract = pair.put if option_type is OptionType.PUT else pair.call
        spread = _spread(leg)
        premium = _premium(leg)
        score = _selection_score(step, leg, spread)
        candidates.append((score, step, pair.strike, contract, leg, spread, premium))
    if not candidates:
        raise OptionContractSelectionError(
            "no valid ATM/ITM option contract available for directional paper selling",
            diagnostics=tuple(diagnostics),
        )

    _, step, strike, contract, leg, spread, premium = _select_candidate(candidates, configuration)
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
            f"Selection policy: {configuration.selection_policy.value}.",
            f"Selected {moneyness.value.upper()} contract at {strike:g} using deterministic liquidity score {round(float(_selection_score(step, leg, spread)), 6):g}.",
        ),
        status="selected",
        selection_policy=configuration.selection_policy,
        selection_diagnostics=tuple(diagnostics),
    )


def _pair_for_step(universe: ZerodhaOptionUniverse, option_type: OptionType, step: int):
    strikes = tuple(pair.strike for pair in universe.pairs)
    atm_index = strikes.index(universe.atm_strike)
    index = atm_index + step if option_type is OptionType.PUT else atm_index - step
    if index < 0 or index >= len(universe.pairs):
        raise ValueError("requested ITM step is outside the option universe")
    return universe.pairs[index]


def _select_candidate(candidates, configuration: DirectionalOptionSellingConfiguration):
    if configuration.selection_policy is OptionPaperSelectionPolicy.PREFERRED_ITM_DEPTH:
        preferred = tuple(item for item in candidates if item[1] == configuration.preferred_itm_step)
        if preferred:
            return sorted(preferred, key=lambda item: (-item[0], item[2]))[0]
    if configuration.selection_policy is OptionPaperSelectionPolicy.BEST_LIQUID_VALID:
        return sorted(candidates, key=lambda item: (-item[0], item[1], item[2]))[0]
    return sorted(candidates, key=lambda item: (item[1], -item[0], item[2]))[0]


def _valid_leg(leg: OptionLeg, configuration: DirectionalOptionSellingConfiguration) -> bool:
    return _leg_rejection_reasons(leg, configuration) == (OptionContractRejectionReason.VALID,)


def _validate_quote_timestamp(
    decision_time,
    quote_time,
    trading_date: date,
    configuration: DirectionalOptionSellingConfiguration,
) -> None:
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise OptionContractSelectionError("trade candidate timestamp must be timezone-aware", stage="OPTION_CHAIN_TIMEZONE_MISMATCH")
    if quote_time.tzinfo is None or quote_time.utcoffset() is None:
        raise OptionContractSelectionError("option chain snapshot timestamp must be timezone-aware", stage="OPTION_CHAIN_TIMEZONE_MISMATCH")
    quote_session_date = quote_time.astimezone(decision_time.tzinfo).date()
    if quote_session_date != trading_date:
        raise OptionContractSelectionError("option chain snapshot trading session does not match runtime trading date", stage="OPTION_CHAIN_SESSION_MISMATCH")
    if quote_time > decision_time + _FUTURE_QUOTE_TOLERANCE:
        raise OptionContractSelectionError("future option premium cannot be selected", stage="OPTION_CHAIN_FUTURE")
    age_seconds = (decision_time - quote_time).total_seconds()
    if age_seconds > configuration.maximum_quote_age_seconds:
        raise OptionContractSelectionError("stale option premium cannot be selected", stage="OPTION_CHAIN_STALE")


def _leg_rejection_reasons(
    leg: OptionLeg,
    configuration: DirectionalOptionSellingConfiguration,
) -> tuple[OptionContractRejectionReason, ...]:
    reasons = []
    if _premium(leg) <= 0:
        reasons.append(OptionContractRejectionReason.INVALID_PREMIUM)
    if leg.open_interest < configuration.minimum_open_interest:
        reasons.append(OptionContractRejectionReason.OI_BELOW_MINIMUM)
    if leg.volume < configuration.minimum_volume:
        reasons.append(OptionContractRejectionReason.VOLUME_BELOW_MINIMUM)
    spread = _spread(leg)
    premium = _premium(leg)
    if spread is not None and premium > 0 and spread / premium > configuration.maximum_spread_fraction:
        reasons.append(OptionContractRejectionReason.SPREAD_TOO_WIDE)
    return tuple(reasons) if reasons else (OptionContractRejectionReason.VALID,)


def _diagnostic(
    strike: float | None,
    option_type: OptionType,
    step: int,
    leg: OptionLeg | None,
    rejection_reasons: tuple[OptionContractRejectionReason, ...],
) -> OptionContractSelectionDiagnostic:
    premium = _premium(leg) if leg is not None else None
    spread = _spread(leg) if leg is not None else None
    spread_fraction = None if leg is None or spread is None or premium is None or premium <= 0 else spread / premium
    return OptionContractSelectionDiagnostic(
        strike=strike,
        option_type=option_type,
        itm_steps=step,
        premium=premium,
        bid=None if leg is None else leg.bid_price,
        ask=None if leg is None else leg.ask_price,
        spread=spread,
        spread_fraction=spread_fraction,
        open_interest=None if leg is None else leg.open_interest,
        volume=None if leg is None else leg.volume,
        status=OptionContractSelectionStatus.VALID
        if rejection_reasons == (OptionContractRejectionReason.VALID,)
        else OptionContractSelectionStatus.REJECTED,
        rejection_reasons=rejection_reasons,
    )


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
    bid_ask_bonus = 1.0 if leg.bid_price is not None and leg.ask_price is not None else 0.0
    return bid_ask_bonus + liquidity + volume - spread_penalty
