"""
Pure calculator for Option Chain Analytics Engine V1.
"""

from core.enums.instrument import Instrument
from engines.option_chain.enums import OptionType, PositioningBias
from engines.option_chain.models import OptionChainSnapshot, OptionChainState, OptionLeg
from engines.option_chain_analytics.classifier import OptionBuildUpClassifier
from engines.option_chain_analytics.configuration import OptionChainAnalyticsConfiguration
from engines.option_chain_analytics.enums import (
    OptionAnalyticsBias,
    OptionBuildUpType,
    OptionLevelMigration,
    OptionPressureType,
    OptionTrendDirection,
)
from engines.option_chain_analytics.models import (
    OptionChainAnalyticsSnapshot,
    OptionLegAnalytics,
    OptionMetricTrend,
    OptionPressureSummary,
    OptionStrikeAnalytics,
)


class OptionChainAnalyticsCalculator:
    def __init__(self, classifier: OptionBuildUpClassifier | None = None):
        self._classifier = classifier or OptionBuildUpClassifier()

    def calculate(
        self,
        *,
        current_snapshot: OptionChainSnapshot,
        current_analysis: OptionChainState,
        previous_snapshot: OptionChainSnapshot | None,
        previous_analysis: OptionChainState | None,
        configuration: OptionChainAnalyticsConfiguration,
    ) -> OptionChainAnalyticsSnapshot:
        _validate_current(current_snapshot, current_analysis, configuration)
        underlying = Instrument.from_symbol(current_analysis.symbol)
        if underlying not in {Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX}:
            raise ValueError("unsupported option analytics underlying")
        if previous_snapshot is not None:
            _validate_previous(current_snapshot, previous_snapshot, previous_analysis)

        previous_legs = _previous_leg_map(previous_snapshot)
        strikes = tuple(
            self._strike_analytics(strike, previous_legs, configuration)
            for strike in current_snapshot.strikes
        )
        pressure = _pressure_summary(strikes, configuration)
        pcr_trend = _trend(current_analysis.oi_pcr, previous_analysis.oi_pcr if previous_analysis else None)
        change_oi_pcr_trend = _trend(
            current_analysis.change_oi_pcr,
            previous_analysis.change_oi_pcr if previous_analysis else None,
        )
        max_pain_trend = _trend(current_analysis.max_pain_strike, previous_analysis.max_pain_strike if previous_analysis else None)
        support_migration = _migration(previous_analysis.support_strike if previous_analysis else None, current_analysis.support_strike)
        resistance_migration = _migration(previous_analysis.resistance_strike if previous_analysis else None, current_analysis.resistance_strike)
        atm_migration = _migration(previous_analysis.atm_strike if previous_analysis else None, current_analysis.atm_strike)
        bullish_score, bearish_score, rationale = _score(
            pressure,
            pcr_trend,
            support_migration,
            resistance_migration,
            atm_migration,
            current_analysis.positioning_bias,
            previous_analysis is not None,
            configuration,
        )
        return OptionChainAnalyticsSnapshot(
            underlying=underlying,
            expiry=current_analysis.expiry_date,
            timestamp=current_analysis.timestamp,
            source_snapshot=current_snapshot,
            source_analysis=current_analysis,
            strikes=strikes,
            pressure=pressure,
            pcr_trend=pcr_trend,
            change_oi_pcr_trend=change_oi_pcr_trend,
            max_pain_trend=max_pain_trend,
            support_migration=support_migration,
            resistance_migration=resistance_migration,
            atm_migration=atm_migration,
            previous_support=previous_analysis.support_strike if previous_analysis else None,
            current_support=current_analysis.support_strike,
            previous_resistance=previous_analysis.resistance_strike if previous_analysis else None,
            current_resistance=current_analysis.resistance_strike,
            previous_atm_strike=previous_analysis.atm_strike if previous_analysis else None,
            current_atm_strike=current_analysis.atm_strike,
            bullish_score=bullish_score,
            bearish_score=bearish_score,
            bias=_bias(bullish_score, bearish_score, previous_analysis is not None, pressure, configuration),
            rationale=tuple(rationale),
        )

    def _strike_analytics(self, strike, previous_legs, configuration):
        call = self._leg_analytics(strike.strike_price, OptionType.CALL, strike.call, previous_legs, configuration)
        put = self._leg_analytics(strike.strike_price, OptionType.PUT, strike.put, previous_legs, configuration)
        net = (put.runtime_change_open_interest if put else 0) - (call.runtime_change_open_interest if call else 0)
        return OptionStrikeAnalytics(
            strike=strike.strike_price,
            call=call,
            put=put,
            net_runtime_oi_change=net,
            dominant_pressure=_strike_pressure(call, put),
        )

    def _leg_analytics(self, strike, side, leg: OptionLeg | None, previous_legs, configuration):
        if leg is None:
            return None
        previous = previous_legs.get((float(strike), side))
        previous_price = previous.last_price if previous else None
        previous_oi = previous.open_interest if previous else None
        price_change = leg.last_price - previous_price if previous_price is not None else None
        oi_delta = leg.open_interest - previous_oi if previous_oi is not None else None
        build_up = self._classifier.classify(
            current_price=leg.last_price,
            previous_price=previous_price,
            runtime_change_open_interest=leg.change_in_open_interest,
            previous_open_interest=previous_oi,
            current_open_interest=leg.open_interest,
            configuration=configuration,
        )
        return OptionLegAnalytics(
            strike=strike,
            side=side,
            current_price=leg.last_price,
            previous_price=previous_price,
            price_change=price_change,
            current_open_interest=leg.open_interest,
            previous_open_interest=previous_oi,
            runtime_change_open_interest=leg.change_in_open_interest,
            open_interest_delta_from_previous_snapshot=oi_delta,
            build_up=build_up,
        )


def analytics_input_from_live_snapshot(live_snapshot):
    from application.live_option_chain import LiveOptionChainSnapshot, LiveOptionChainStatus

    if not isinstance(live_snapshot, LiveOptionChainSnapshot):
        raise TypeError("live_snapshot must be LiveOptionChainSnapshot")
    if live_snapshot.status is not LiveOptionChainStatus.READY:
        raise ValueError("live option-chain snapshot must be READY")
    if live_snapshot.latest_option_chain_snapshot is None:
        raise ValueError("live snapshot has no option-chain source snapshot")
    if live_snapshot.latest_option_chain_analysis is None:
        raise ValueError("live snapshot has no option-chain analysis")
    return live_snapshot.latest_option_chain_snapshot, live_snapshot.latest_option_chain_analysis


def _validate_current(snapshot, analysis, configuration):
    if not isinstance(snapshot, OptionChainSnapshot):
        raise TypeError("current_snapshot must be OptionChainSnapshot")
    if not isinstance(analysis, OptionChainState):
        raise TypeError("current_analysis must be OptionChainState")
    if not isinstance(configuration, OptionChainAnalyticsConfiguration):
        raise TypeError("configuration must be OptionChainAnalyticsConfiguration")
    if snapshot.symbol != analysis.symbol or snapshot.expiry_date != analysis.expiry_date:
        raise ValueError("current snapshot and analysis context mismatch")
    if snapshot.timestamp != analysis.timestamp:
        raise ValueError("current snapshot and analysis timestamp mismatch")


def _validate_previous(current, previous, previous_analysis):
    if not isinstance(previous, OptionChainSnapshot):
        raise TypeError("previous_snapshot must be OptionChainSnapshot")
    if not isinstance(previous_analysis, OptionChainState):
        raise TypeError("previous_analysis is required with previous_snapshot")
    if previous.symbol != current.symbol or previous.expiry_date != current.expiry_date:
        raise ValueError("previous option-chain context mismatch")
    if previous_analysis.symbol != current.symbol or previous_analysis.expiry_date != current.expiry_date:
        raise ValueError("previous analysis context mismatch")


def _previous_leg_map(previous_snapshot):
    result = {}
    if previous_snapshot is None:
        return result
    for strike in previous_snapshot.strikes:
        if strike.call is not None:
            result[(float(strike.strike_price), OptionType.CALL)] = strike.call
        if strike.put is not None:
            result[(float(strike.strike_price), OptionType.PUT)] = strike.put
    return result


def _pressure_summary(strikes, configuration):
    call_writing = put_writing = call_unwinding = put_unwinding = 0
    call_short_buildup_count = put_short_buildup_count = 0
    call_short_covering_count = put_short_covering_count = 0
    comparable = False
    for strike in strikes:
        for leg in (strike.call, strike.put):
            if leg is None or leg.build_up is OptionBuildUpType.INSUFFICIENT_DATA:
                continue
            comparable = True
            if leg.side is OptionType.CALL and leg.build_up is OptionBuildUpType.SHORT_BUILDUP and leg.runtime_change_open_interest > 0:
                call_writing += leg.runtime_change_open_interest
                call_short_buildup_count += 1
            if leg.side is OptionType.PUT and leg.build_up is OptionBuildUpType.SHORT_BUILDUP and leg.runtime_change_open_interest > 0:
                put_writing += leg.runtime_change_open_interest
                put_short_buildup_count += 1
            if leg.side is OptionType.CALL and leg.build_up is OptionBuildUpType.SHORT_COVERING and leg.runtime_change_open_interest < 0:
                call_unwinding += abs(leg.runtime_change_open_interest)
                call_short_covering_count += 1
            if leg.side is OptionType.PUT and leg.build_up is OptionBuildUpType.SHORT_COVERING and leg.runtime_change_open_interest < 0:
                put_unwinding += abs(leg.runtime_change_open_interest)
                put_short_covering_count += 1
    ratio = put_writing / call_writing if call_writing > 0 and put_writing > 0 else None
    dominant = _dominant_pressure(
        comparable,
        call_writing,
        put_writing,
        call_unwinding,
        put_unwinding,
        configuration,
    )
    return OptionPressureSummary(
        call_writing,
        put_writing,
        call_unwinding,
        put_unwinding,
        call_short_buildup_count,
        put_short_buildup_count,
        call_short_covering_count,
        put_short_covering_count,
        ratio,
        dominant,
    )


def _dominant_pressure(comparable, call_writing, put_writing, call_unwinding, put_unwinding, configuration):
    if not comparable:
        return OptionPressureType.INSUFFICIENT_DATA
    totals = {
        OptionPressureType.CALL_WRITING: call_writing,
        OptionPressureType.PUT_WRITING: put_writing,
        OptionPressureType.CALL_UNWINDING: call_unwinding,
        OptionPressureType.PUT_UNWINDING: put_unwinding,
    }
    max_value = max(totals.values())
    if max_value == 0:
        return OptionPressureType.BALANCED
    leaders = [key for key, value in totals.items() if value == max_value]
    if len(leaders) > 1:
        return OptionPressureType.MIXED
    leader = leaders[0]
    writing = call_writing + put_writing
    unwinding = call_unwinding + put_unwinding
    if writing and unwinding and abs(writing - unwinding) <= max(writing, unwinding) / configuration.strong_pressure_ratio:
        return OptionPressureType.MIXED
    if call_writing and put_writing:
        ratio = max(call_writing, put_writing) / min(call_writing, put_writing)
        if ratio < configuration.strong_pressure_ratio:
            return OptionPressureType.BALANCED
    return leader


def _trend(current, previous):
    if current is None or previous is None:
        return OptionMetricTrend(current, previous, None, OptionTrendDirection.UNKNOWN)
    change = float(current) - float(previous)
    if change > 0:
        direction = OptionTrendDirection.RISING
    elif change < 0:
        direction = OptionTrendDirection.FALLING
    else:
        direction = OptionTrendDirection.FLAT
    return OptionMetricTrend(current, previous, change, direction)


def _migration(previous, current):
    if previous is None and current is None:
        return OptionLevelMigration.UNKNOWN
    if previous is None:
        return OptionLevelMigration.APPEARED
    if current is None:
        return OptionLevelMigration.DISAPPEARED
    if current > previous:
        return OptionLevelMigration.SHIFTED_UP
    if current < previous:
        return OptionLevelMigration.SHIFTED_DOWN
    return OptionLevelMigration.UNCHANGED


def _score(pressure, pcr_trend, support, resistance, atm, positioning_bias, has_previous, configuration):
    bullish = bearish = 0
    rationale = []
    if pressure.dominant_pressure is OptionPressureType.PUT_WRITING:
        bullish += 2
        rationale.append("Put writing exceeds call writing.")
    elif pressure.dominant_pressure is OptionPressureType.CALL_WRITING:
        bearish += 2
        rationale.append("Call writing dominates current positioning.")
    elif pressure.dominant_pressure is OptionPressureType.CALL_UNWINDING:
        bullish += 2
        rationale.append("Call unwinding supports bullish positioning.")
    elif pressure.dominant_pressure is OptionPressureType.PUT_UNWINDING:
        bearish += 2
        rationale.append("Put unwinding supports bearish positioning.")
    elif pressure.dominant_pressure is OptionPressureType.INSUFFICIENT_DATA:
        rationale.append("Previous comparable snapshot is unavailable.")
    else:
        rationale.append("Writing pressure is balanced or mixed.")

    if pcr_trend.direction is OptionTrendDirection.RISING:
        bullish += 1
        rationale.append("OI PCR is rising.")
    elif pcr_trend.direction is OptionTrendDirection.FALLING:
        bearish += 1
        rationale.append("OI PCR is falling.")

    for migration, name in ((support, "Support"), (resistance, "Resistance"), (atm, "ATM strike")):
        if migration is OptionLevelMigration.SHIFTED_UP:
            bullish += 1
            rationale.append(f"{name} shifted upward.")
        elif migration is OptionLevelMigration.SHIFTED_DOWN:
            bearish += 1
            rationale.append(f"{name} shifted downward.")
        elif migration is OptionLevelMigration.UNCHANGED:
            rationale.append(f"{name} remained unchanged.")

    if positioning_bias is PositioningBias.BULLISH:
        bullish += 1
        rationale.append("Existing option-chain bias is bullish.")
    elif positioning_bias is PositioningBias.BEARISH:
        bearish += 1
        rationale.append("Existing option-chain bias is bearish.")

    return bullish, bearish, rationale


def _bias(bullish, bearish, has_previous, pressure, configuration):
    if not has_previous and pressure.dominant_pressure is OptionPressureType.INSUFFICIENT_DATA:
        return OptionAnalyticsBias.INSUFFICIENT_DATA
    if bullish >= configuration.strong_bias_score and bearish == 0:
        return OptionAnalyticsBias.STRONGLY_BULLISH
    if bearish >= configuration.strong_bias_score and bullish == 0:
        return OptionAnalyticsBias.STRONGLY_BEARISH
    if bullish > 0 and bearish > 0 and abs(bullish - bearish) <= 1:
        return OptionAnalyticsBias.CONFLICTED
    if bullish > bearish:
        return OptionAnalyticsBias.BULLISH
    if bearish > bullish:
        return OptionAnalyticsBias.BEARISH
    if bullish == 0 and bearish == 0:
        return OptionAnalyticsBias.NEUTRAL
    return OptionAnalyticsBias.CONFLICTED


def _strike_pressure(call, put):
    values = []
    for leg in (call, put):
        if leg is None:
            continue
        if leg.side is OptionType.CALL and leg.build_up is OptionBuildUpType.SHORT_BUILDUP:
            values.append(OptionPressureType.CALL_WRITING)
        elif leg.side is OptionType.PUT and leg.build_up is OptionBuildUpType.SHORT_BUILDUP:
            values.append(OptionPressureType.PUT_WRITING)
        elif leg.side is OptionType.CALL and leg.build_up is OptionBuildUpType.SHORT_COVERING:
            values.append(OptionPressureType.CALL_UNWINDING)
        elif leg.side is OptionType.PUT and leg.build_up is OptionBuildUpType.SHORT_COVERING:
            values.append(OptionPressureType.PUT_UNWINDING)
    if not values:
        if any(leg and leg.build_up is OptionBuildUpType.INSUFFICIENT_DATA for leg in (call, put)):
            return OptionPressureType.INSUFFICIENT_DATA
        return OptionPressureType.BALANCED
    if len(set(values)) > 1:
        return OptionPressureType.MIXED
    return values[0]
