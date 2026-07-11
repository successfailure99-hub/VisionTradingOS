"""
Stateless Market Context Engine V1 calculations.
"""

from engines.market_context.enums import (
    AgreementState,
    CamarillaZone,
    ContextStrength,
    CPRPosition,
    EvidenceDirection,
    MarketBias,
    MarketPhase,
    VWAPPosition,
)
from engines.market_context.models import ContextEvidence, MarketContextSnapshot, MarketContextState
from engines.option_chain.enums import PositioningBias
from engines.price_action.enums import BreakType, Trend


class MarketContextCalculator:
    """
    Combines already-calculated context into a deterministic summary.

    Price Action and Option Chain are primary. VWAP, CPR, and Camarilla
    are secondary confirmations. The calculator describes context and
    conflict, does not produce trades, and performs no persistence,
    broker access, historical analysis, or AI interpretation.
    """

    SOURCE_ORDER = ("price_action", "option_chain", "vwap", "cpr", "camarilla")

    @staticmethod
    def calculate(snapshot: MarketContextSnapshot) -> MarketContextState:
        price_action_direction = MarketContextCalculator._price_action_direction(snapshot)
        option_chain_direction = MarketContextCalculator._option_chain_direction(snapshot)
        vwap_position, vwap_direction = MarketContextCalculator._vwap_context(snapshot)
        cpr_position, cpr_direction, virgin_cpr = MarketContextCalculator._cpr_context(snapshot)
        camarilla_zone, camarilla_direction = MarketContextCalculator._camarilla_context(snapshot)

        agreement = MarketContextCalculator._agreement(price_action_direction, option_chain_direction)
        market_bias = MarketContextCalculator._market_bias(price_action_direction, option_chain_direction)
        market_phase = MarketContextCalculator._market_phase(snapshot)

        evidence = (
            ContextEvidence(
                "price_action",
                price_action_direction,
                MarketContextCalculator._detail("price_action", price_action_direction),
            ),
            ContextEvidence(
                "option_chain",
                option_chain_direction,
                MarketContextCalculator._detail("option_chain", option_chain_direction),
            ),
            ContextEvidence("vwap", vwap_direction, MarketContextCalculator._vwap_detail(vwap_position)),
            ContextEvidence("cpr", cpr_direction, MarketContextCalculator._cpr_detail(cpr_position)),
            ContextEvidence(
                "camarilla",
                camarilla_direction,
                MarketContextCalculator._camarilla_detail(camarilla_zone),
            ),
        )

        bullish_count = MarketContextCalculator._count(evidence, EvidenceDirection.BULLISH)
        bearish_count = MarketContextCalculator._count(evidence, EvidenceDirection.BEARISH)
        neutral_count = MarketContextCalculator._count(evidence, EvidenceDirection.NEUTRAL)
        mixed_count = MarketContextCalculator._count(evidence, EvidenceDirection.MIXED)
        available_count = sum(1 for item in evidence if item.direction is not EvidenceDirection.UNKNOWN)
        missing_sources = tuple(
            source
            for source in MarketContextCalculator.SOURCE_ORDER
            if getattr(snapshot, source) is None
        )
        strength = MarketContextCalculator._strength(
            market_bias,
            agreement,
            price_action_direction,
            option_chain_direction,
            (vwap_direction, cpr_direction, camarilla_direction),
        )

        return MarketContextState(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            timestamp=snapshot.timestamp,
            current_price=snapshot.current_price,
            session_high=snapshot.session_high,
            session_low=snapshot.session_low,
            market_bias=market_bias,
            market_phase=market_phase,
            agreement=agreement,
            context_strength=strength,
            price_action_direction=price_action_direction,
            option_chain_direction=option_chain_direction,
            vwap_position=vwap_position,
            cpr_position=cpr_position,
            virgin_cpr=virgin_cpr,
            camarilla_zone=camarilla_zone,
            bullish_evidence_count=bullish_count,
            bearish_evidence_count=bearish_count,
            neutral_evidence_count=neutral_count,
            mixed_evidence_count=mixed_count,
            available_source_count=available_count,
            evidence=evidence,
            missing_sources=missing_sources,
        )

    @staticmethod
    def _price_action_direction(snapshot: MarketContextSnapshot) -> EvidenceDirection:
        if snapshot.price_action is None:
            return EvidenceDirection.UNKNOWN
        mapping = {
            Trend.BULLISH: EvidenceDirection.BULLISH,
            Trend.BEARISH: EvidenceDirection.BEARISH,
            Trend.RANGE: EvidenceDirection.NEUTRAL,
            Trend.UNKNOWN: EvidenceDirection.UNKNOWN,
        }
        return mapping[snapshot.price_action.trend]

    @staticmethod
    def _option_chain_direction(snapshot: MarketContextSnapshot) -> EvidenceDirection:
        if snapshot.option_chain is None:
            return EvidenceDirection.UNKNOWN
        mapping = {
            PositioningBias.BULLISH: EvidenceDirection.BULLISH,
            PositioningBias.BEARISH: EvidenceDirection.BEARISH,
            PositioningBias.NEUTRAL: EvidenceDirection.NEUTRAL,
            PositioningBias.MIXED: EvidenceDirection.MIXED,
            PositioningBias.UNKNOWN: EvidenceDirection.UNKNOWN,
        }
        return mapping[snapshot.option_chain.positioning_bias]

    @staticmethod
    def _vwap_context(snapshot: MarketContextSnapshot) -> tuple[VWAPPosition, EvidenceDirection]:
        if snapshot.vwap is None:
            return VWAPPosition.UNAVAILABLE, EvidenceDirection.UNKNOWN
        if snapshot.current_price > snapshot.vwap.vwap:
            return VWAPPosition.ABOVE, EvidenceDirection.BULLISH
        if snapshot.current_price < snapshot.vwap.vwap:
            return VWAPPosition.BELOW, EvidenceDirection.BEARISH
        return VWAPPosition.AT, EvidenceDirection.NEUTRAL

    @staticmethod
    def _cpr_context(snapshot: MarketContextSnapshot) -> tuple[CPRPosition, EvidenceDirection, bool | None]:
        if snapshot.cpr is None:
            return CPRPosition.UNAVAILABLE, EvidenceDirection.UNKNOWN, None
        if snapshot.current_price > snapshot.cpr.tc:
            position = CPRPosition.ABOVE
            direction = EvidenceDirection.BULLISH
        elif snapshot.current_price < snapshot.cpr.bc:
            position = CPRPosition.BELOW
            direction = EvidenceDirection.BEARISH
        else:
            position = CPRPosition.INSIDE
            direction = EvidenceDirection.NEUTRAL
        touched = snapshot.session_high >= snapshot.cpr.bc and snapshot.session_low <= snapshot.cpr.tc
        return position, direction, not touched

    @staticmethod
    def _camarilla_context(snapshot: MarketContextSnapshot) -> tuple[CamarillaZone, EvidenceDirection]:
        if snapshot.camarilla is None:
            return CamarillaZone.UNAVAILABLE, EvidenceDirection.UNKNOWN
        price = snapshot.current_price
        levels = snapshot.camarilla
        if price > levels.h6:
            zone = CamarillaZone.ABOVE_H6
        elif levels.h5 < price <= levels.h6:
            zone = CamarillaZone.H5_TO_H6
        elif levels.h4 < price <= levels.h5:
            zone = CamarillaZone.H4_TO_H5
        elif levels.h3 < price <= levels.h4:
            zone = CamarillaZone.H3_TO_H4
        elif levels.l3 <= price <= levels.h3:
            zone = CamarillaZone.L3_TO_H3
        elif levels.l4 <= price < levels.l3:
            zone = CamarillaZone.L4_TO_L3
        elif levels.l5 <= price < levels.l4:
            zone = CamarillaZone.L5_TO_L4
        elif levels.l6 <= price < levels.l5:
            zone = CamarillaZone.L6_TO_L5
        else:
            zone = CamarillaZone.BELOW_L6
        return zone, MarketContextCalculator._camarilla_direction(zone)

    @staticmethod
    def _camarilla_direction(zone: CamarillaZone) -> EvidenceDirection:
        if zone in {
            CamarillaZone.ABOVE_H6,
            CamarillaZone.H5_TO_H6,
            CamarillaZone.H4_TO_H5,
            CamarillaZone.H3_TO_H4,
        }:
            return EvidenceDirection.BULLISH
        if zone is CamarillaZone.L3_TO_H3:
            return EvidenceDirection.NEUTRAL
        if zone is CamarillaZone.UNAVAILABLE:
            return EvidenceDirection.UNKNOWN
        return EvidenceDirection.BEARISH

    @staticmethod
    def _agreement(pa_direction: EvidenceDirection, oc_direction: EvidenceDirection) -> AgreementState:
        directional = {EvidenceDirection.BULLISH, EvidenceDirection.BEARISH}
        if pa_direction in directional and oc_direction in directional:
            if pa_direction is oc_direction:
                return AgreementState.ALIGNED
            return AgreementState.CONFLICTED
        if pa_direction is EvidenceDirection.UNKNOWN and oc_direction is EvidenceDirection.UNKNOWN:
            return AgreementState.INSUFFICIENT
        if pa_direction in directional or oc_direction in directional:
            return AgreementState.PARTIAL
        return AgreementState.PARTIAL

    @staticmethod
    def _market_bias(pa_direction: EvidenceDirection, oc_direction: EvidenceDirection) -> MarketBias:
        directions = (pa_direction, oc_direction)
        if EvidenceDirection.BULLISH in directions and EvidenceDirection.BEARISH in directions:
            return MarketBias.MIXED
        if EvidenceDirection.BULLISH in directions:
            return MarketBias.BULLISH
        if EvidenceDirection.BEARISH in directions:
            return MarketBias.BEARISH
        if EvidenceDirection.MIXED in directions:
            return MarketBias.MIXED
        if EvidenceDirection.NEUTRAL in directions:
            return MarketBias.NEUTRAL
        return MarketBias.UNKNOWN

    @staticmethod
    def _market_phase(snapshot: MarketContextSnapshot) -> MarketPhase:
        state = snapshot.price_action
        if state is None:
            return MarketPhase.UNKNOWN
        latest_break = state.latest_break
        if (
            latest_break is not None
            and latest_break.candle_start_time == state.last_candle.start_time
            and latest_break.candle_end_time == state.last_candle.end_time
        ):
            mapping = {
                BreakType.BULLISH_CHOCH: MarketPhase.REVERSAL_UP,
                BreakType.BEARISH_CHOCH: MarketPhase.REVERSAL_DOWN,
                BreakType.BULLISH_BOS: MarketPhase.BREAKOUT_UP,
                BreakType.BEARISH_BOS: MarketPhase.BREAKOUT_DOWN,
            }
            return mapping[latest_break.break_type]
        mapping = {
            Trend.BULLISH: MarketPhase.TRENDING_UP,
            Trend.BEARISH: MarketPhase.TRENDING_DOWN,
            Trend.RANGE: MarketPhase.RANGE,
            Trend.UNKNOWN: MarketPhase.UNKNOWN,
        }
        return mapping[state.trend]

    @staticmethod
    def _strength(
        market_bias: MarketBias,
        agreement: AgreementState,
        pa_direction: EvidenceDirection,
        oc_direction: EvidenceDirection,
        secondary_directions: tuple[EvidenceDirection, EvidenceDirection, EvidenceDirection],
    ) -> ContextStrength:
        if agreement is AgreementState.INSUFFICIENT or market_bias is MarketBias.UNKNOWN:
            return ContextStrength.INSUFFICIENT
        if agreement is AgreementState.CONFLICTED:
            return ContextStrength.WEAK
        target = None
        if market_bias is MarketBias.BULLISH:
            target = EvidenceDirection.BULLISH
        elif market_bias is MarketBias.BEARISH:
            target = EvidenceDirection.BEARISH
        if target is None:
            return ContextStrength.WEAK
        confirmations = sum(1 for direction in secondary_directions if direction is target)
        opposition = any(
            direction in {EvidenceDirection.BULLISH, EvidenceDirection.BEARISH}
            and direction is not target
            for direction in secondary_directions
        )
        if agreement is AgreementState.ALIGNED:
            if confirmations >= 2 and not opposition:
                return ContextStrength.STRONG
            return ContextStrength.MODERATE
        if agreement is AgreementState.PARTIAL:
            if confirmations >= 2 and not opposition:
                return ContextStrength.MODERATE
            return ContextStrength.WEAK
        return ContextStrength.WEAK

    @staticmethod
    def _count(evidence: tuple[ContextEvidence, ...], direction: EvidenceDirection) -> int:
        return sum(1 for item in evidence if item.direction is direction)

    @staticmethod
    def _detail(source: str, direction: EvidenceDirection) -> str:
        return f"{source}_direction_{direction.value}"

    @staticmethod
    def _vwap_detail(position: VWAPPosition) -> str:
        if position is VWAPPosition.UNAVAILABLE:
            return "vwap_unavailable"
        return f"price_{position.value}_vwap"

    @staticmethod
    def _cpr_detail(position: CPRPosition) -> str:
        if position is CPRPosition.UNAVAILABLE:
            return "cpr_unavailable"
        return f"price_{position.value}_cpr"

    @staticmethod
    def _camarilla_detail(zone: CamarillaZone) -> str:
        if zone is CamarillaZone.UNAVAILABLE:
            return "camarilla_unavailable"
        return f"price_{zone.value}"