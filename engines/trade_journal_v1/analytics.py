"""
Stateless Trade Performance Analytics V1 calculator.
"""

from collections import defaultdict
from datetime import datetime
from math import isclose

from core.enums.instrument import Instrument
from engines.strategy_decision_v2.enums import StrategySetupFamily
from engines.trade_journal_v1.configuration import TradeJournalV1Configuration
from engines.trade_journal_v1.enums import PerformanceTrend, TradeOutcome
from engines.trade_journal_v1.models import (
    ConfidenceBucketPerformance,
    EquityCurvePoint,
    InstrumentPerformance,
    SetupPerformance,
    TradeJournalEntry,
    TradePerformanceAnalyticsSnapshot,
    TradePerformanceStatistics,
)


INSTRUMENT_ORDER = (Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX)
CONFIDENCE_BUCKETS = (
    ("0.00-0.49", 0.0, 0.49),
    ("0.50-0.69", 0.50, 0.69),
    ("0.70-0.84", 0.70, 0.84),
    ("0.85-1.00", 0.85, 1.0),
)


class TradePerformanceAnalyticsCalculator:
    def calculate(
        self,
        entries: tuple[TradeJournalEntry, ...],
        configuration: TradeJournalV1Configuration,
        *,
        timestamp: datetime,
    ) -> TradePerformanceAnalyticsSnapshot:
        if not isinstance(configuration, TradeJournalV1Configuration):
            raise TypeError("configuration must be TradeJournalV1Configuration")
        items = tuple(entries)
        if any(not isinstance(item, TradeJournalEntry) for item in items):
            raise TypeError("entries must contain TradeJournalEntry")
        equity_curve = _equity_curve(items, configuration.equity_curve_limit)
        overall = _statistics(items, equity_curve, configuration)
        by_instrument = _instrument_statistics(items, configuration) if configuration.calculate_instrument_statistics else ()
        by_setup = _setup_statistics(items, configuration) if configuration.calculate_setup_statistics else ()
        by_confidence = _confidence_statistics(items, configuration) if configuration.calculate_confidence_statistics else ()
        return TradePerformanceAnalyticsSnapshot(
            timestamp=timestamp,
            overall=overall,
            by_instrument=by_instrument,
            by_setup=by_setup,
            by_confidence=by_confidence,
            equity_curve=equity_curve,
            best_instrument=_best_instrument(by_instrument),
            worst_instrument=_worst_instrument(by_instrument),
            best_setup=_best_setup(by_setup),
            worst_setup=_worst_setup(by_setup),
            last_trade=items[-1] if items else None,
        )


def _statistics(entries, equity_curve, configuration):
    count = len(entries)
    wins = [entry.realized_pnl for entry in entries if entry.outcome is TradeOutcome.WIN]
    losses = [entry.realized_pnl for entry in entries if entry.outcome is TradeOutcome.LOSS]
    flats = [entry.realized_pnl for entry in entries if entry.outcome is TradeOutcome.FLAT]
    total = sum(entry.realized_pnl for entry in entries)
    gross_profit = sum(value for value in wins if value > 0.0)
    gross_loss = abs(sum(value for value in losses if value < 0.0))
    net = gross_profit - gross_loss
    win_rate = len(wins) / count if count else None
    loss_rate = len(losses) / count if count else None
    average_win = sum(wins) / len(wins) if wins else None
    average_loss = sum(losses) / len(losses) if losses else None
    expectancy = None
    if count and average_win is not None and average_loss is not None and win_rate is not None and loss_rate is not None:
        expectancy = (win_rate * average_win) + (loss_rate * average_loss)
    elif count and average_win is not None and win_rate is not None:
        expectancy = win_rate * average_win
    elif count and average_loss is not None and loss_rate is not None:
        expectancy = loss_rate * average_loss
    r_values = [entry.r_multiple for entry in entries if entry.r_multiple is not None]
    max_drawdown = max((point.drawdown_amount for point in equity_curve), default=0.0)
    current_win, current_loss, max_win, max_loss = _streaks(entries)
    return TradePerformanceStatistics(
        trade_count=count,
        win_count=len(wins),
        loss_count=len(losses),
        flat_count=len(flats),
        win_rate=win_rate,
        loss_rate=loss_rate,
        total_pnl=total,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_pnl=net,
        average_trade=net / count if count else None,
        average_win=average_win,
        average_loss=average_loss,
        largest_win=max(wins) if wins else None,
        largest_loss=min(losses) if losses else None,
        expectancy=expectancy,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0.0 else None,
        average_r_multiple=sum(r_values) / len(r_values) if r_values else None,
        maximum_r_multiple=max(r_values) if r_values else None,
        minimum_r_multiple=min(r_values) if r_values else None,
        maximum_drawdown_amount=max_drawdown,
        maximum_drawdown_fraction=None,
        current_winning_streak=current_win,
        current_losing_streak=current_loss,
        maximum_winning_streak=max_win,
        maximum_losing_streak=max_loss,
        trend=_trend(entries, configuration),
    )


def _equity_curve(entries, limit):
    points = []
    cumulative = 0.0
    peak = 0.0
    for sequence, entry in enumerate(entries, start=1):
        cumulative += entry.realized_pnl
        peak = max(peak, cumulative)
        points.append(
            EquityCurvePoint(
                sequence,
                entry.closed_at,
                entry.trade_id,
                entry.realized_pnl,
                cumulative,
                peak,
                peak - cumulative,
                None,
            )
        )
    return tuple(points[-limit:])


def _streaks(entries):
    current_win = current_loss = max_win = max_loss = 0
    for entry in entries:
        if entry.outcome is TradeOutcome.WIN:
            current_win += 1
            current_loss = 0
        elif entry.outcome is TradeOutcome.LOSS:
            current_loss += 1
            current_win = 0
        else:
            current_win = current_loss = 0
        max_win = max(max_win, current_win)
        max_loss = max(max_loss, current_loss)
    return current_win, current_loss, max_win, max_loss


def _trend(entries, configuration):
    if len(entries) < configuration.minimum_trades_for_trend:
        return PerformanceTrend.INSUFFICIENT_DATA
    half = len(entries) // 2
    earlier = entries[:half]
    latest = entries[-half:]
    earlier_avg = sum(entry.realized_pnl for entry in earlier) / len(earlier)
    latest_avg = sum(entry.realized_pnl for entry in latest) / len(latest)
    if latest_avg > earlier_avg + configuration.flat_pnl_tolerance:
        return PerformanceTrend.IMPROVING
    if latest_avg < earlier_avg - configuration.flat_pnl_tolerance:
        return PerformanceTrend.DECLINING
    return PerformanceTrend.STABLE


def _instrument_statistics(entries, configuration):
    grouped = defaultdict(list)
    for entry in entries:
        grouped[entry.instrument].append(entry)
    return tuple(
        InstrumentPerformance(
            instrument,
            _statistics(tuple(grouped[instrument]), _equity_curve(tuple(grouped[instrument]), configuration.equity_curve_limit), configuration),
        )
        for instrument in INSTRUMENT_ORDER
        if grouped[instrument]
    )


def _setup_statistics(entries, configuration):
    grouped = defaultdict(list)
    for entry in entries:
        grouped[entry.setup_family].append(entry)
    return tuple(
        SetupPerformance(
            setup,
            _statistics(tuple(grouped[setup]), _equity_curve(tuple(grouped[setup]), configuration.equity_curve_limit), configuration),
        )
        for setup in StrategySetupFamily
        if grouped[setup]
    )


def _confidence_statistics(entries, configuration):
    return tuple(
        ConfidenceBucketPerformance(
            label,
            minimum,
            maximum,
            _statistics(
                tuple(entry for entry in entries if _in_bucket(entry.reasoning_confidence, minimum, maximum)),
                _equity_curve(tuple(entry for entry in entries if _in_bucket(entry.reasoning_confidence, minimum, maximum)), configuration.equity_curve_limit),
                configuration,
            ),
        )
        for label, minimum, maximum in CONFIDENCE_BUCKETS
    )


def _in_bucket(confidence, minimum, maximum):
    if maximum == 1.0:
        return minimum <= confidence <= maximum
    return minimum <= confidence <= maximum or isclose(confidence, maximum)


def _best_instrument(items):
    winners = [item for item in items if item.statistics.trade_count]
    return max(winners, key=lambda item: item.statistics.net_pnl).instrument if winners else None


def _worst_instrument(items):
    winners = [item for item in items if item.statistics.trade_count]
    return min(winners, key=lambda item: item.statistics.net_pnl).instrument if winners else None


def _best_setup(items):
    winners = [item for item in items if item.statistics.trade_count]
    return max(winners, key=lambda item: item.statistics.net_pnl).setup_family if winners else None


def _worst_setup(items):
    winners = [item for item in items if item.statistics.trade_count]
    return min(winners, key=lambda item: item.statistics.net_pnl).setup_family if winners else None
