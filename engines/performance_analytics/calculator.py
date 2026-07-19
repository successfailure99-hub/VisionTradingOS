"""
Pure performance analytics calculations for PaperTradeRecord sequences.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from engines.paper_trading.models import PaperTradeRecord
from engines.performance_analytics.configuration import PerformanceAnalyticsConfiguration
from engines.performance_analytics.enums import AnalyticsGroupType, AnalyticsPeriod, ReviewClassification
from engines.performance_analytics.models import (
    AnalyticsDiagnostics,
    AnalyticsFilters,
    AnalyticsSnapshot,
    EquityCurvePoint,
    GroupPerformance,
    PerformanceSummary,
    PeriodPerformance,
    PostTradeReview,
    TradeReplayMetadata,
)


IST = ZoneInfo("Asia/Kolkata")
INSTRUMENT_ORDER = ("NIFTY", "BANKNIFTY", "SENSEX")
TIME_BUCKETS = (
    ("09:15-10:00", (9, 15), (10, 0)),
    ("10:00-11:00", (10, 0), (11, 0)),
    ("11:00-12:00", (11, 0), (12, 0)),
    ("12:00-13:00", (12, 0), (13, 0)),
    ("13:00-14:00", (13, 0), (14, 0)),
    ("14:00-15:00", (14, 0), (15, 0)),
    ("15:00-15:30", (15, 0), (15, 30)),
)


class PerformanceAnalyticsCalculator:
    def calculate(
        self,
        records: tuple[PaperTradeRecord, ...],
        configuration: PerformanceAnalyticsConfiguration,
        *,
        instrument: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        generated_at: datetime | None = None,
        diagnostics: AnalyticsDiagnostics | None = None,
    ) -> AnalyticsSnapshot:
        if not isinstance(configuration, PerformanceAnalyticsConfiguration):
            raise TypeError("configuration must be PerformanceAnalyticsConfiguration")
        ordered = _ordered(records)
        filtered = _filter_records(ordered, instrument=instrument, start_date=start_date, end_date=end_date)
        return AnalyticsSnapshot(
            overall=summary(ordered, configuration),
            selected_instrument=summary(filtered, configuration),
            equity_curve=equity_curve(filtered, configuration),
            daily_performance=_periods(filtered, configuration, AnalyticsPeriod.DAILY),
            weekly_performance=_periods(filtered, configuration, AnalyticsPeriod.WEEKLY),
            monthly_performance=_periods(filtered, configuration, AnalyticsPeriod.MONTHLY),
            instrument_statistics=_groups(ordered, configuration, AnalyticsGroupType.INSTRUMENT, lambda r: r.instrument),
            direction_statistics=_groups(filtered, configuration, AnalyticsGroupType.DIRECTION, lambda r: _value(r.direction)),
            setup_statistics=_groups(filtered, configuration, AnalyticsGroupType.SETUP, lambda r: r.strategy_setup or "-"),
            entry_type_statistics=_groups(filtered, configuration, AnalyticsGroupType.ENTRY_TYPE, lambda r: getattr(r, "entry_type", "-") or "-"),
            exit_type_statistics=_groups(filtered, configuration, AnalyticsGroupType.EXIT_TYPE, lambda r: _value(r.exit_type)),
            time_of_day_statistics=_groups(filtered, configuration, AnalyticsGroupType.TIME_OF_DAY, _time_bucket),
            camarilla_statistics=_groups(filtered, configuration, AnalyticsGroupType.CAMARILLA, lambda r: getattr(r, "camarilla_relationship", "-") or "-"),
            cpr_statistics=_groups(filtered, configuration, AnalyticsGroupType.CPR, lambda r: getattr(r, "cpr_relationship", "-") or "-"),
            ai_confidence_statistics=_groups(filtered, configuration, AnalyticsGroupType.AI_CONFIDENCE, _ai_bucket),
            latest_records=tuple(reversed(filtered[-configuration.recent_trade_limit :])),
            filters_applied=AnalyticsFilters(instrument, start_date, end_date),
            generated_at=generated_at,
            diagnostics=diagnostics or AnalyticsDiagnostics(),
        )


def summary(records: tuple[PaperTradeRecord, ...], configuration: PerformanceAnalyticsConfiguration) -> PerformanceSummary:
    ordered = _ordered(records)
    count = len(ordered)
    wins = tuple(record for record in ordered if record.net_pnl > 0)
    losses = tuple(record for record in ordered if record.net_pnl < 0)
    flats = tuple(record for record in ordered if record.net_pnl == 0)
    gross_profit = sum(record.net_pnl for record in wins)
    gross_loss = abs(sum(record.net_pnl for record in losses))
    net = sum(record.net_pnl for record in ordered)
    r_values = tuple(record.reward_risk_realized for record in ordered if record.reward_risk_realized is not None)
    curve = equity_curve(ordered, configuration)
    current_win, current_loss, max_win, max_loss = _streaks(ordered)
    return PerformanceSummary(
        record_count=count,
        winning_trades=len(wins),
        losing_trades=len(losses),
        breakeven_trades=len(flats),
        win_rate=(len(wins) / count * 100) if count else None,
        loss_rate=(len(losses) / count * 100) if count else None,
        breakeven_rate=(len(flats) / count * 100) if count else None,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit=net,
        total_fees=sum(record.fees for record in ordered),
        average_trade=(net / count) if count else None,
        average_win=(gross_profit / len(wins)) if wins else None,
        average_loss=(-(gross_loss / len(losses))) if losses else None,
        largest_win=max((record.net_pnl for record in wins), default=None),
        largest_loss=min((record.net_pnl for record in losses), default=None),
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else None,
        expectancy=(net / count) if count else None,
        expectancy_r=(sum(r_values) / len(r_values)) if r_values else None,
        average_r=(sum(r_values) / len(r_values)) if r_values else None,
        median_r=median(r_values) if r_values else None,
        best_r=max(r_values) if r_values else None,
        worst_r=min(r_values) if r_values else None,
        payoff_ratio=((gross_profit / len(wins)) / (gross_loss / len(losses))) if wins and losses and gross_loss > 0 else None,
        maximum_drawdown=max((point.drawdown for point in curve), default=0.0),
        maximum_drawdown_percentage=max((point.drawdown_percentage for point in curve), default=0.0),
        current_drawdown=curve[-1].drawdown if curve else 0.0,
        current_drawdown_percentage=curve[-1].drawdown_percentage if curve else 0.0,
        consecutive_wins=current_win,
        consecutive_losses=current_loss,
        maximum_consecutive_wins=max_win,
        maximum_consecutive_losses=max_loss,
        average_holding_seconds=(sum(record.holding_seconds for record in ordered) / count) if count else None,
        average_mfe=(sum(record.maximum_favourable_excursion for record in ordered) / count) if count else None,
        average_mae=(sum(record.maximum_adverse_excursion for record in ordered) / count) if count else None,
        start_time=ordered[0].entry_time if ordered else None,
        end_time=ordered[-1].exit_time if ordered else None,
    )


def equity_curve(records: tuple[PaperTradeRecord, ...], configuration: PerformanceAnalyticsConfiguration) -> tuple[EquityCurvePoint, ...]:
    cumulative = 0.0
    running_peak = 0.0
    running_peak_equity = configuration.starting_equity
    points = []
    for sequence, record in enumerate(_ordered(records), start=1):
        cumulative += record.net_pnl
        running_peak = max(0.0, running_peak, cumulative)
        drawdown = running_peak - cumulative
        equity = configuration.starting_equity + cumulative
        running_peak_equity = max(configuration.starting_equity, running_peak_equity, equity)
        drawdown_percentage = ((running_peak_equity - equity) / running_peak_equity * 100) if running_peak_equity > 0 else 0.0
        points.append(
            EquityCurvePoint(
                sequence=sequence,
                trade_id=record.trade_id,
                instrument=record.instrument,
                timestamp=record.exit_time,
                trade_pnl=record.net_pnl,
                cumulative_pnl=cumulative,
                running_peak=running_peak,
                drawdown=drawdown,
                drawdown_percentage=drawdown_percentage,
            )
        )
    return tuple(points)


def post_trade_review(record: PaperTradeRecord) -> PostTradeReview:
    classification = ReviewClassification.WIN if record.net_pnl > 0 else ReviewClassification.LOSS if record.net_pnl < 0 else ReviewClassification.BREAKEVEN
    planned_risk = abs(record.entry_price - record.stop_price) * record.quantity
    planned_reward = abs(record.target_price - record.entry_price) * record.quantity
    execution_efficiency = record.net_pnl / planned_reward if planned_reward > 0 else None
    mfe_capture = record.net_pnl / record.maximum_favourable_excursion if record.maximum_favourable_excursion > 0 else None
    mae_relative = record.maximum_adverse_excursion / planned_risk if planned_risk > 0 else None
    tags = []
    if _value(record.exit_type) == "TARGET":
        tags.append("TARGET_EXIT")
    if _value(record.exit_type) == "STOP_LOSS":
        tags.append("STOP_EXIT")
    if record.reward_risk_realized is not None and record.reward_risk_realized > 0:
        tags.append("POSITIVE_R")
    if record.reward_risk_realized is not None and record.reward_risk_realized < 0:
        tags.append("NEGATIVE_R")
    if mfe_capture is not None and mfe_capture < 0.35:
        tags.append("LOW_MFE_CAPTURE")
    if mae_relative is not None and mae_relative >= 1.0:
        tags.append("HIGH_MAE")
    if record.holding_seconds <= 300:
        tags.append("QUICK_EXIT")
    if record.holding_seconds >= 3600:
        tags.append("EXTENDED_HOLD")
    tags.append("PLAN_FOLLOWED")
    if not getattr(record, "strategy_setup", None) or record.strategy_setup == "-":
        tags.append("MISSING_CONTEXT")
    return PostTradeReview(
        trade_id=record.trade_id,
        classification=classification,
        planned_r=record.reward_risk_planned,
        realized_r=record.reward_risk_realized,
        execution_efficiency=execution_efficiency,
        mfe_capture_ratio=mfe_capture,
        mae_relative_to_planned_risk=mae_relative,
        exit_assessment=f"Exit recorded as {_value(record.exit_type)}.",
        setup_assessment=f"Setup context: {record.strategy_setup or '-'}.",
        process_observations=("Review is derived from stored paper-trade facts only.",),
        positive_observations=tuple(item for item in ("Positive R captured." if record.net_pnl > 0 else "",) if item),
        improvement_observations=tuple(item for item in ("Review missing setup context." if "MISSING_CONTEXT" in tags else "",) if item),
        review_tags=tuple(dict.fromkeys(tags)),
    )


def replay_metadata(record: PaperTradeRecord) -> TradeReplayMetadata:
    return TradeReplayMetadata(
        trade_id=record.trade_id,
        plan_id=record.plan_id,
        instrument=record.instrument,
        timeframe=getattr(record, "timeframe", None),
        trading_date=record.trading_date,
        entry_time=record.entry_time,
        exit_time=record.exit_time,
        direction=_value(record.direction),
        entry_price=record.entry_price,
        stop_price=record.stop_price,
        target_price=record.target_price,
        exit_price=record.exit_price,
        entry_type=getattr(record, "entry_type", "-"),
        strategy_setup=record.strategy_setup,
        strategy_reasoning=record.strategy_reasoning,
        ai_reasoning=getattr(record, "ai_reasoning_summary", None),
        market_context_labels=tuple(_present(getattr(record, name, None)) for name in ("market_phase", "day_bias")),
        option_chain_labels=tuple(_present(getattr(record, name, None)) for name in ("option_chain_bias",)),
        cpr_labels=tuple(_present(getattr(record, name, None)) for name in ("cpr_relationship", "cpr_width_classification")),
        camarilla_labels=tuple(_present(getattr(record, name, None)) for name in ("camarilla_relationship",)),
        vwap_labels=tuple(_present(getattr(record, name, None)) for name in ("vwap_relationship",)),
        source_strategy_id=getattr(record, "source_strategy_id", "-"),
        source_plan_identity=getattr(record, "source_plan_identity", "-"),
    )


def _ordered(records):
    items = tuple(records)
    if any(not isinstance(item, PaperTradeRecord) for item in items):
        raise TypeError("records must contain PaperTradeRecord")
    return tuple(sorted(items, key=lambda item: (item.exit_time, item.trade_id)))


def _filter_records(records, *, instrument=None, start_date=None, end_date=None):
    normalized = instrument.upper() if isinstance(instrument, str) and instrument.strip() else None
    return tuple(
        record
        for record in records
        if (normalized is None or record.instrument == normalized)
        and (start_date is None or record.trading_date >= start_date)
        and (end_date is None or record.trading_date <= end_date)
    )


def _periods(records, configuration, period):
    grouped = defaultdict(list)
    for record in _ordered(records):
        key = _period_key(record, period)
        grouped[key].append(record)
    return tuple(
        PeriodPerformance(
            period=period,
            label=label,
            period_start=start,
            period_end=end,
            summary=summary(tuple(grouped[(label, start, end)]), configuration),
        )
        for label, start, end in sorted(grouped)
    )


def _period_key(record, period):
    day = record.trading_date
    if period is AnalyticsPeriod.DAILY:
        return day.isoformat(), day, day
    if period is AnalyticsPeriod.WEEKLY:
        iso = day.isocalendar()
        start = day - timedelta(days=day.weekday())
        end = start + timedelta(days=6)
        return f"{iso.year}-W{iso.week:02d}", start, end
    start = day.replace(day=1)
    end = (start.replace(year=start.year + 1, month=1, day=1) if start.month == 12 else start.replace(month=start.month + 1, day=1)) - timedelta(days=1)
    return f"{day.year}-{day.month:02d}", start, end


def _groups(records, configuration, group_type, key_func):
    grouped = defaultdict(list)
    for record in _ordered(records):
        grouped[str(key_func(record) or "-")].append(record)
    return tuple(
        GroupPerformance(group_type, key, summary(tuple(grouped[key]), configuration))
        for key in sorted(grouped)
    )


def _streaks(records):
    current_win = current_loss = max_win = max_loss = 0
    for record in records:
        if record.net_pnl > 0:
            current_win += 1
            current_loss = 0
        elif record.net_pnl < 0:
            current_loss += 1
            current_win = 0
        else:
            current_win = current_loss = 0
        max_win = max(max_win, current_win)
        max_loss = max(max_loss, current_loss)
    return current_win, current_loss, max_win, max_loss


def _time_bucket(record):
    t = record.entry_time.astimezone(IST).time()
    for label, start, end in TIME_BUCKETS:
        start_t = t.replace(hour=start[0], minute=start[1], second=0, microsecond=0)
        end_t = t.replace(hour=end[0], minute=end[1], second=0, microsecond=0)
        if start_t <= t < end_t or (label == "15:00-15:30" and t == end_t):
            return label
    return "Outside Session"


def _ai_bucket(record):
    value = getattr(record, "ai_confidence", None)
    if value is None:
        return "Unknown"
    if value < 0.5:
        return "0.00-0.49"
    if value < 0.7:
        return "0.50-0.69"
    if value < 0.85:
        return "0.70-0.84"
    return "0.85-1.00"


def _value(value):
    return str(getattr(value, "value", value)).strip() or "-"


def _present(value):
    text = str(value).strip() if value is not None else ""
    return text or "-"
