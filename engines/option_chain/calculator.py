"""
Stateless Option Chain Engine V1 calculations.
"""

from engines.option_chain.enums import PositioningBias, PressureType
from engines.option_chain.models import (
    OptionChainSnapshot,
    OptionChainState,
    OptionStrike,
    StrikeMetric,
)


class OptionChainCalculator:
    """
    Calculates objective option-chain positioning from complete snapshots.

    V1 is broker-independent and assumes inputs are already validated and
    sorted. ATM uses the nearest available strike. OI support and
    resistance are positioning references. Max Pain is calculated from
    open-interest payout minimization. Pressure uses aggregate signed
    change in OI, and positioning bias is descriptive rather than a
    trade signal.
    """

    @staticmethod
    def calculate(snapshot: OptionChainSnapshot) -> OptionChainState:
        strikes = snapshot.strikes

        atm_strike = min(
            strikes,
            key=lambda strike: (
                abs(strike.strike_price - snapshot.underlying_price),
                strike.strike_price,
            ),
        ).strike_price

        total_call_oi = sum(strike.call.open_interest for strike in strikes if strike.call is not None)
        total_put_oi = sum(strike.put.open_interest for strike in strikes if strike.put is not None)
        total_call_change_oi = sum(
            strike.call.change_in_open_interest for strike in strikes if strike.call is not None
        )
        total_put_change_oi = sum(
            strike.put.change_in_open_interest for strike in strikes if strike.put is not None
        )

        positive_call_change = sum(
            max(strike.call.change_in_open_interest, 0)
            for strike in strikes
            if strike.call is not None
        )
        positive_put_change = sum(
            max(strike.put.change_in_open_interest, 0)
            for strike in strikes
            if strike.put is not None
        )

        oi_pcr = None
        if total_call_oi > 0:
            oi_pcr = round(total_put_oi / total_call_oi, 4)

        change_oi_pcr = None
        if positive_call_change > 0:
            change_oi_pcr = round(positive_put_change / positive_call_change, 4)

        max_call_oi = OptionChainCalculator._max_call_oi(strikes)
        max_put_oi = OptionChainCalculator._max_put_oi(strikes)
        max_call_change_oi = OptionChainCalculator._max_call_change_oi(strikes)
        max_put_change_oi = OptionChainCalculator._max_put_change_oi(strikes)

        call_pressure = OptionChainCalculator._call_pressure(strikes, total_call_change_oi)
        put_pressure = OptionChainCalculator._put_pressure(strikes, total_put_change_oi)
        positioning_bias = OptionChainCalculator._positioning_bias(call_pressure, put_pressure)

        return OptionChainState(
            symbol=snapshot.symbol,
            exchange=snapshot.exchange,
            expiry_date=snapshot.expiry_date,
            timestamp=snapshot.timestamp,
            underlying_price=snapshot.underlying_price,
            atm_strike=atm_strike,
            strike_count=len(strikes),
            total_call_oi=total_call_oi,
            total_put_oi=total_put_oi,
            total_call_change_oi=total_call_change_oi,
            total_put_change_oi=total_put_change_oi,
            oi_pcr=oi_pcr,
            change_oi_pcr=change_oi_pcr,
            max_call_oi=max_call_oi,
            max_put_oi=max_put_oi,
            max_call_change_oi=max_call_change_oi,
            max_put_change_oi=max_put_change_oi,
            resistance_strike=max_call_oi.strike_price if max_call_oi is not None else None,
            support_strike=max_put_oi.strike_price if max_put_oi is not None else None,
            max_pain_strike=OptionChainCalculator._max_pain(strikes, snapshot.underlying_price),
            call_pressure=call_pressure,
            put_pressure=put_pressure,
            positioning_bias=positioning_bias,
            strikes=strikes,
        )

    @staticmethod
    def _max_call_oi(strikes: tuple[OptionStrike, ...]) -> StrikeMetric | None:
        call_strikes = [strike for strike in strikes if strike.call is not None]
        if not call_strikes:
            return None

        selected = max(call_strikes, key=lambda strike: (strike.call.open_interest, -strike.strike_price))
        return StrikeMetric(selected.strike_price, selected.call.open_interest)

    @staticmethod
    def _max_put_oi(strikes: tuple[OptionStrike, ...]) -> StrikeMetric | None:
        put_strikes = [strike for strike in strikes if strike.put is not None]
        if not put_strikes:
            return None

        selected = max(put_strikes, key=lambda strike: (strike.put.open_interest, strike.strike_price))
        return StrikeMetric(selected.strike_price, selected.put.open_interest)

    @staticmethod
    def _max_call_change_oi(strikes: tuple[OptionStrike, ...]) -> StrikeMetric | None:
        call_strikes = [
            strike
            for strike in strikes
            if strike.call is not None and strike.call.change_in_open_interest > 0
        ]
        if not call_strikes:
            return None

        selected = max(
            call_strikes,
            key=lambda strike: (strike.call.change_in_open_interest, -strike.strike_price),
        )
        return StrikeMetric(selected.strike_price, selected.call.change_in_open_interest)

    @staticmethod
    def _max_put_change_oi(strikes: tuple[OptionStrike, ...]) -> StrikeMetric | None:
        put_strikes = [
            strike
            for strike in strikes
            if strike.put is not None and strike.put.change_in_open_interest > 0
        ]
        if not put_strikes:
            return None

        selected = max(
            put_strikes,
            key=lambda strike: (strike.put.change_in_open_interest, strike.strike_price),
        )
        return StrikeMetric(selected.strike_price, selected.put.change_in_open_interest)

    @staticmethod
    def _max_pain(strikes: tuple[OptionStrike, ...], underlying_price: float) -> float:
        def payout(candidate: float) -> float:
            total = 0.0
            for strike in strikes:
                if strike.call is not None:
                    total += max(candidate - strike.strike_price, 0) * strike.call.open_interest
                if strike.put is not None:
                    total += max(strike.strike_price - candidate, 0) * strike.put.open_interest
            return total

        return min(
            (strike.strike_price for strike in strikes),
            key=lambda candidate: (
                payout(candidate),
                abs(candidate - underlying_price),
                candidate,
            ),
        )

    @staticmethod
    def _call_pressure(strikes: tuple[OptionStrike, ...], total_change_oi: int) -> PressureType:
        has_call = any(strike.call is not None for strike in strikes)
        if not has_call:
            return PressureType.UNKNOWN
        if total_change_oi > 0:
            return PressureType.CALL_WRITING
        if total_change_oi < 0:
            return PressureType.CALL_UNWINDING
        return PressureType.BALANCED

    @staticmethod
    def _put_pressure(strikes: tuple[OptionStrike, ...], total_change_oi: int) -> PressureType:
        has_put = any(strike.put is not None for strike in strikes)
        if not has_put:
            return PressureType.UNKNOWN
        if total_change_oi > 0:
            return PressureType.PUT_WRITING
        if total_change_oi < 0:
            return PressureType.PUT_UNWINDING
        return PressureType.BALANCED

    @staticmethod
    def _positioning_bias(
        call_pressure: PressureType,
        put_pressure: PressureType,
    ) -> PositioningBias:
        if call_pressure is PressureType.UNKNOWN or put_pressure is PressureType.UNKNOWN:
            return PositioningBias.UNKNOWN

        if (
            put_pressure is PressureType.PUT_WRITING
            and call_pressure in {PressureType.CALL_UNWINDING, PressureType.BALANCED}
        ):
            return PositioningBias.BULLISH

        if (
            call_pressure is PressureType.CALL_WRITING
            and put_pressure in {PressureType.PUT_UNWINDING, PressureType.BALANCED}
        ):
            return PositioningBias.BEARISH

        if call_pressure is PressureType.BALANCED and put_pressure is PressureType.BALANCED:
            return PositioningBias.NEUTRAL

        return PositioningBias.MIXED