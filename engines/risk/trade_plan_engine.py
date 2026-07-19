"""
Risk Management and Trade Plan Engine V1.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta
from math import floor, isfinite
from zoneinfo import ZoneInfo

from engines.ai_reasoning.enums import ReasoningConfidence, TradingSuitability
from engines.market_context.enums import AgreementState
from engines.risk.enums import RiskDecision, RiskRejectionReason, RiskReductionReason, RiskTier
from engines.risk.models import DailyRiskState, RiskConfiguration, RiskDecisionState, RiskEvaluation, TradePlan
from engines.strategy.enums import BlockReason, StrategyDecision, TradeDirection


IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)


class RiskTradePlanEngine:
    def __init__(self):
        self._active_plan: TradePlan | None = None
        self._active_state: RiskDecisionState | None = None
        self._daily_state: DailyRiskState | None = None
        self._latest_evaluation: RiskEvaluation | None = None

    @property
    def active_plan(self) -> TradePlan | None:
        return self._active_plan

    @property
    def daily_state(self) -> DailyRiskState | None:
        return self._daily_state

    @property
    def latest_evaluation(self) -> RiskEvaluation | None:
        return self._latest_evaluation

    def reset(self) -> None:
        self._active_plan = None
        self._active_state = None
        self._daily_state = None
        self._latest_evaluation = None

    def record_paper_trade_close(self, *, realized_pnl: float) -> RiskDecisionState | None:
        if self._daily_state is None or self._active_state is None:
            return self._active_state
        reserved = self._active_plan.risk_amount if self._active_plan is not None else 0.0
        self._daily_state = replace(
            self._daily_state,
            trades_completed=self._daily_state.trades_completed + 1,
            realized_pnl=round(self._daily_state.realized_pnl + float(realized_pnl), 2),
            risk_reserved=round(max(0.0, self._daily_state.risk_reserved - reserved), 2),
        )
        self._active_state = replace(
            self._active_state,
            realized_pnl_today=round(self._daily_state.realized_pnl, 2),
            remaining_daily_loss_capacity=round(max(self._active_state.daily_loss_limit_amount + self._daily_state.realized_pnl, 0), 2),
        )
        return self._active_state

    def evaluate(
        self,
        *,
        symbol: str,
        timeframe: str,
        strategy,
        configuration: RiskConfiguration,
        market_context=None,
        price_action=None,
        option_chain=None,
        camarilla=None,
        cpr=None,
        latest_tick=None,
        position=None,
        now: datetime | None = None,
    ) -> RiskDecisionState:
        if not isinstance(configuration, RiskConfiguration):
            raise TypeError("configuration must be RiskConfiguration")
        evaluated_at = _aware(now or getattr(strategy, "timestamp", None))
        self._reset_daily_if_needed(evaluated_at)
        symbol = symbol.strip().upper()
        gate = self._first_gate_failure(
            symbol=symbol,
            strategy=strategy,
            configuration=configuration,
            market_context=market_context,
            price_action=price_action,
            option_chain=option_chain,
            latest_tick=latest_tick,
            position=position,
            evaluated_at=evaluated_at,
        )
        if gate is not None:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, gate)

        levels = _resolve_levels(strategy, market_context, price_action, camarilla, cpr)
        if levels.entry is None:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "ENTRY_UNAVAILABLE")
        if levels.stop is None:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "STOP_UNAVAILABLE", entry=levels.entry)
        if levels.target is None:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "TARGET_UNAVAILABLE", entry=levels.entry, stop=levels.stop)

        geometry = _geometry(strategy.direction, levels.entry, levels.stop, levels.target)
        if geometry is None:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "INVALID_PRICE_GEOMETRY", entry=levels.entry, stop=levels.stop, target=levels.target)
        stop_distance, target_distance, reward_risk = geometry
        if stop_distance == 0:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "INVALID_PRICE_GEOMETRY", entry=levels.entry, stop=levels.stop, target=levels.target)
        if stop_distance / levels.entry * 100 > configuration.maximum_stop_distance_percentage:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "STOP_TOO_WIDE", entry=levels.entry, stop=levels.stop, target=levels.target, rr=reward_risk)
        if reward_risk < configuration.minimum_reward_risk:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "REWARD_RISK_TOO_LOW", entry=levels.entry, stop=levels.stop, target=levels.target, rr=reward_risk)

        if configuration.capital is None:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "CAPITAL_UNAVAILABLE", entry=levels.entry, stop=levels.stop, target=levels.target, rr=reward_risk)
        risk_budget = configuration.risk_budget
        if risk_budget is None or risk_budget <= 0:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "RISK_BUDGET_EXHAUSTED", entry=levels.entry, stop=levels.stop, target=levels.target, rr=reward_risk)
        lot_size = configuration.lot_size_for(symbol)
        if lot_size is None:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "LOT_SIZE_UNAVAILABLE", entry=levels.entry, stop=levels.stop, target=levels.target, rr=reward_risk)

        raw_quantity = floor(risk_budget / stop_distance)
        raw_lots = floor(raw_quantity / lot_size)
        approved_lots = min(raw_lots, configuration.maximum_lots)
        if approved_lots <= 0:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "QUANTITY_BELOW_ONE_LOT", entry=levels.entry, stop=levels.stop, target=levels.target, rr=reward_risk, lot_size=lot_size)
        approved_quantity = approved_lots * lot_size
        estimated_risk = round(approved_quantity * stop_distance, 2)
        estimated_reward = round(approved_quantity * target_distance, 2)
        if estimated_risk > risk_budget:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "RISK_BUDGET_EXHAUSTED", entry=levels.entry, stop=levels.stop, target=levels.target, rr=reward_risk, lot_size=lot_size)
        if self._daily_state.plans_approved >= configuration.maximum_trades_per_day:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "DAILY_TRADE_LIMIT", entry=levels.entry, stop=levels.stop, target=levels.target, rr=reward_risk, lot_size=lot_size)
        if configuration.maximum_daily_loss > 0 and -self._daily_state.realized_pnl >= configuration.maximum_daily_loss:
            return self._reject(symbol, timeframe, strategy, configuration, evaluated_at, "DAILY_LOSS_LIMIT", entry=levels.entry, stop=levels.stop, target=levels.target, rr=reward_risk, lot_size=lot_size)

        plan_id = _plan_id(symbol, strategy, levels.entry, levels.stop, levels.target)
        if (
            self._active_plan is not None
            and self._active_state is not None
            and self._active_plan.plan_id == plan_id
            and self._active_plan.valid_until > evaluated_at
        ):
            self._latest_evaluation = self._evaluation(
                symbol,
                evaluated_at,
                True,
                "APPROVED",
                "STANDARD",
                "NONE",
                "Trade plan ready",
                configuration,
                levels.entry,
                levels.stop,
                levels.target,
                stop_distance,
                target_distance,
                reward_risk,
                lot_size,
                approved_lots,
                approved_quantity,
                estimated_risk,
                estimated_reward,
            )
            return self._active_state

        valid_until = evaluated_at + timedelta(minutes=configuration.trade_plan_validity_minutes)
        plan = TradePlan(
            plan_id=plan_id,
            instrument=symbol,
            created_at=evaluated_at,
            strategy_direction=strategy.direction,
            strategy_setup=strategy.setup_quality.value,
            entry_type=strategy.entry_reference.value,
            entry_price=levels.entry,
            stop_price=levels.stop,
            target_price=levels.target,
            lot_size=lot_size,
            approved_lots=approved_lots,
            approved_quantity=approved_quantity,
            risk_amount=estimated_risk,
            reward_amount=estimated_reward,
            reward_risk=round(reward_risk, 4),
            valid_from=evaluated_at,
            valid_until=valid_until,
            status="READY",
            reasoning=("risk_approved", f"approved_lots_{approved_lots}"),
            source_strategy_id=_strategy_id(symbol, strategy),
        )
        self._active_plan = plan
        self._daily_state = replace(
            self._daily_state,
            plans_approved=self._daily_state.plans_approved + 1,
            risk_reserved=round(self._daily_state.risk_reserved + estimated_risk, 2),
        )
        state = self._approved_state(
            symbol,
            timeframe,
            strategy,
            configuration,
            plan,
            stop_distance,
            target_distance,
            risk_budget,
        )
        self._active_state = state
        self._latest_evaluation = self._evaluation(
            symbol,
            evaluated_at,
            True,
            "APPROVED",
            "STANDARD",
            "NONE",
            "Trade plan ready",
            configuration,
            levels.entry,
            levels.stop,
            levels.target,
            stop_distance,
            target_distance,
            reward_risk,
            lot_size,
            approved_lots,
            approved_quantity,
            estimated_risk,
            estimated_reward,
        )
        return state

    def _first_gate_failure(self, *, symbol, strategy, configuration, market_context, price_action, option_chain, latest_tick, position, evaluated_at):
        if strategy is None:
            return "ANALYSIS_NOT_READY"
        if getattr(strategy, "symbol", "").strip().upper() != symbol:
            return "ANALYSIS_NOT_READY"
        if strategy.decision is not StrategyDecision.TRADE_ELIGIBLE or strategy.block_reason is not BlockReason.NONE:
            return "STRATEGY_NOT_ELIGIBLE"
        if price_action is None:
            return "PRICE_ACTION_UNAVAILABLE"
        if option_chain is None:
            return "OPTION_CHAIN_UNAVAILABLE"
        if market_context is None:
            return "ANALYSIS_NOT_READY"
        if (evaluated_at - _aware(strategy.timestamp)).total_seconds() > configuration.max_data_age_seconds:
            return "STALE_DATA"
        if not _session_allowed(evaluated_at, configuration):
            return "OUTSIDE_SESSION"
        if strategy.confidence is ReasoningConfidence.LOW and not configuration.allow_low_confidence:
            return "LOW_CONFIDENCE"
        if strategy.trading_suitability is TradingSuitability.UNSUITABLE:
            return "UNSUITABLE_MARKET"
        if getattr(market_context, "agreement", None) is AgreementState.CONFLICTED and not configuration.allow_mixed_signals:
            return "MIXED_SIGNALS_BLOCKED"
        if position is not None and getattr(position, "absolute_quantity", 0) > 0:
            return "POSITION_ALREADY_ACTIVE"
        if latest_tick is not None and getattr(latest_tick, "symbol", None) is not None and latest_tick.symbol.value != symbol:
            return "ANALYSIS_NOT_READY"
        return None

    def _approved_state(self, symbol, timeframe, strategy, configuration, plan, stop_distance, target_distance, risk_budget):
        return RiskDecisionState(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=plan.created_at,
            decision=RiskDecision.APPROVED,
            risk_tier=RiskTier.STANDARD,
            rejection_reason=RiskRejectionReason.NONE,
            reduction_reason=RiskReductionReason.NONE,
            direction=strategy.direction,
            account_equity=round(configuration.capital, 2),
            realized_pnl_today=round(self._daily_state.realized_pnl, 2),
            daily_loss_limit_amount=round(configuration.maximum_daily_loss, 2),
            remaining_daily_loss_capacity=round(max(configuration.maximum_daily_loss + self._daily_state.realized_pnl, 0), 2),
            applied_risk_percent=configuration.risk_per_trade_percentage,
            risk_budget=risk_budget,
            entry_price=plan.entry_price,
            stop_price=plan.stop_price,
            target_price=plan.target_price,
            stop_distance=round(stop_distance, 4),
            target_distance=round(target_distance, 4),
            reward_risk_ratio=plan.reward_risk,
            lot_size=plan.lot_size,
            requested_lots=plan.approved_lots,
            maximum_permitted_lots=configuration.maximum_lots,
            approved_lots=plan.approved_lots,
            approved_quantity=plan.approved_quantity,
            estimated_risk_amount=plan.risk_amount,
            estimated_reward_amount=plan.reward_amount,
            rationale=plan.reasoning,
            plan_id=plan.plan_id,
            plan_status=plan.status,
            valid_until=plan.valid_until,
            risk_reason="Trade plan ready",
            trade_plan_ready=True,
        )

    def _reject(self, symbol, timeframe, strategy, configuration, evaluated_at, code, *, entry=None, stop=None, target=None, rr=None, lot_size=None):
        reason = _reason_text(code, configuration)
        state = RiskDecisionState(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=evaluated_at,
            decision=RiskDecision.REJECTED,
            risk_tier=RiskTier.BLOCKED,
            rejection_reason=_legacy_rejection_reason(code),
            reduction_reason=RiskReductionReason.NONE,
            direction=getattr(strategy, "direction", TradeDirection.NONE),
            account_equity=round(configuration.capital, 2) if configuration.capital is not None else 0.0,
            realized_pnl_today=round(self._daily_state.realized_pnl, 2),
            daily_loss_limit_amount=round(configuration.maximum_daily_loss, 2),
            remaining_daily_loss_capacity=round(max(configuration.maximum_daily_loss + self._daily_state.realized_pnl, 0), 2),
            applied_risk_percent=configuration.risk_per_trade_percentage,
            risk_budget=configuration.risk_budget or 0.0,
            entry_price=entry or 0.0,
            stop_price=stop or 0.0,
            target_price=target or 0.0,
            stop_distance=abs((entry or 0.0) - (stop or 0.0)) if entry and stop else 0.0,
            target_distance=abs((target or 0.0) - (entry or 0.0)) if entry and target else 0.0,
            reward_risk_ratio=round(rr, 4) if rr else 0.0,
            lot_size=lot_size or 0,
            requested_lots=0,
            maximum_permitted_lots=configuration.maximum_lots,
            approved_lots=0,
            approved_quantity=0,
            estimated_risk_amount=0.0,
            estimated_reward_amount=0.0,
            rationale=(f"rejected_{code.lower()}",),
            plan_status="REJECTED",
            risk_reason=reason,
            trade_plan_ready=False,
        )
        self._active_state = state
        self._latest_evaluation = self._evaluation(
            symbol,
            evaluated_at,
            False,
            "REJECTED",
            "BLOCKED",
            code,
            reason,
            configuration,
            entry,
            stop,
            target,
            state.stop_distance or None,
            state.target_distance or None,
            state.reward_risk_ratio or None,
            lot_size,
            0,
            0,
            0.0,
            0.0,
        )
        return state

    def _evaluation(self, symbol, evaluated_at, approved, status, risk_level, code, reason, configuration, entry, stop, target, stop_distance, target_distance, rr, lot_size, approved_lots, approved_quantity, risk_amount, reward_amount):
        remaining = None
        if configuration.maximum_daily_loss > 0:
            remaining = round(max(configuration.maximum_daily_loss + self._daily_state.realized_pnl, 0), 2)
        return RiskEvaluation(
            instrument=symbol,
            evaluated_at=evaluated_at,
            approved=approved,
            status=status,
            risk_level=risk_level,
            rejection_code=code,
            rejection_reason=reason,
            warnings=(),
            capital=configuration.capital,
            risk_budget=configuration.risk_budget,
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            stop_distance=stop_distance,
            target_distance=target_distance,
            reward_risk=rr,
            lot_size=lot_size,
            requested_lots=approved_lots,
            approved_lots=approved_lots,
            approved_quantity=approved_quantity,
            estimated_risk_amount=risk_amount,
            estimated_reward_amount=reward_amount,
            daily_trade_count=self._daily_state.plans_approved,
            daily_realized_pnl=self._daily_state.realized_pnl,
            daily_remaining_risk=remaining,
        )

    def _reset_daily_if_needed(self, evaluated_at: datetime) -> None:
        trading_date = evaluated_at.astimezone(IST).date()
        if self._daily_state is None or self._daily_state.trading_date != trading_date:
            self._daily_state = DailyRiskState(trading_date)
            self._active_plan = None
            self._active_state = None


class _Levels:
    def __init__(self, entry, stop, target):
        self.entry = entry
        self.stop = stop
        self.target = target


def _resolve_levels(strategy, market_context, price_action, camarilla, cpr) -> _Levels:
    entry = _positive(getattr(market_context, "current_price", None))
    if strategy.direction is TradeDirection.BULLISH:
        stop = _first_positive(
            getattr(getattr(price_action, "latest_hl", None), "price", None),
            getattr(getattr(price_action, "latest_swing_low", None), "price", None),
            getattr(price_action, "current_structure_low", None),
            getattr(cpr, "bc", None),
            getattr(camarilla, "l3", None),
        )
        target = _next_above(entry, (
            getattr(camarilla, "h3", None),
            getattr(camarilla, "h4", None),
            getattr(camarilla, "h5", None),
            getattr(camarilla, "h6", None),
            getattr(price_action, "current_structure_high", None),
            getattr(market_context, "session_high", None),
        ))
        return _Levels(entry, stop, target)
    if strategy.direction is TradeDirection.BEARISH:
        stop = _first_positive(
            getattr(getattr(price_action, "latest_lh", None), "price", None),
            getattr(getattr(price_action, "latest_swing_high", None), "price", None),
            getattr(price_action, "current_structure_high", None),
            getattr(cpr, "tc", None),
            getattr(camarilla, "h3", None),
        )
        target = _next_below(entry, (
            getattr(camarilla, "l3", None),
            getattr(camarilla, "l4", None),
            getattr(camarilla, "l5", None),
            getattr(camarilla, "l6", None),
            getattr(price_action, "current_structure_low", None),
            getattr(market_context, "session_low", None),
        ))
        return _Levels(entry, stop, target)
    return _Levels(entry, None, None)


def _geometry(direction, entry, stop, target):
    if direction is TradeDirection.BULLISH and stop < entry < target:
        stop_distance = entry - stop
        target_distance = target - entry
        return stop_distance, target_distance, target_distance / stop_distance
    if direction is TradeDirection.BEARISH and target < entry < stop:
        stop_distance = stop - entry
        target_distance = entry - target
        return stop_distance, target_distance, target_distance / stop_distance
    return None


def _session_allowed(value: datetime, configuration: RiskConfiguration) -> bool:
    local = value.astimezone(IST)
    if local.weekday() >= 5:
        return False
    if "LIVE" not in configuration.allowed_market_sessions:
        return False
    return SESSION_OPEN <= local.time() <= SESSION_CLOSE


def _first_positive(*values):
    for value in values:
        number = _positive(value)
        if number is not None:
            return number
    return None


def _next_above(entry, values):
    candidates = sorted(number for number in (_positive(value) for value in values) if number is not None and entry is not None and number > entry)
    return candidates[0] if candidates else None


def _next_below(entry, values):
    candidates = sorted((number for number in (_positive(value) for value in values) if number is not None and entry is not None and number < entry), reverse=True)
    return candidates[0] if candidates else None


def _positive(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) and number > 0 else None


def _aware(value) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("timestamp is required")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=IST)
    return value


def _plan_id(symbol, strategy, entry, stop, target) -> str:
    return f"{symbol}:{strategy.timestamp.isoformat()}:{strategy.direction.value}:{entry:.2f}:{stop:.2f}:{target:.2f}"


def _strategy_id(symbol, strategy) -> str:
    return f"{symbol}:{strategy.timestamp.isoformat()}:{strategy.decision.value}:{strategy.direction.value}:{strategy.setup_quality.value}"


def _legacy_rejection_reason(code: str) -> RiskRejectionReason:
    if code == "STRATEGY_NOT_ELIGIBLE":
        return RiskRejectionReason.STRATEGY_NO_TRADE
    if code in {"INVALID_PRICE_GEOMETRY", "ENTRY_UNAVAILABLE", "STOP_UNAVAILABLE", "TARGET_UNAVAILABLE"}:
        return RiskRejectionReason.INVALID_PRICE_STRUCTURE
    if code == "REWARD_RISK_TOO_LOW":
        return RiskRejectionReason.REWARD_RISK_BELOW_MINIMUM
    if code == "DAILY_TRADE_LIMIT":
        return RiskRejectionReason.DAILY_TRADE_LIMIT_REACHED
    if code == "DAILY_LOSS_LIMIT":
        return RiskRejectionReason.DAILY_LOSS_LIMIT_REACHED
    if code in {"CAPITAL_UNAVAILABLE", "RISK_BUDGET_EXHAUSTED", "LOT_SIZE_UNAVAILABLE", "QUANTITY_BELOW_ONE_LOT"}:
        return RiskRejectionReason.INSUFFICIENT_RISK_BUDGET
    return RiskRejectionReason.INVALID_PRICE_STRUCTURE


def _reason_text(code: str, configuration: RiskConfiguration) -> str:
    messages = {
        "ANALYSIS_NOT_READY": "Analysis not ready",
        "STRATEGY_NOT_ELIGIBLE": "Strategy is not trade eligible",
        "PRICE_ACTION_UNAVAILABLE": "Price Action evidence is required",
        "OPTION_CHAIN_UNAVAILABLE": "Option Chain evidence is required",
        "STALE_DATA": "Market data is stale",
        "OUTSIDE_SESSION": "Outside allowed market session",
        "LOW_CONFIDENCE": "AI confidence below risk threshold",
        "MIXED_SIGNALS_BLOCKED": "Mixed signals blocked by risk policy",
        "UNSUITABLE_MARKET": "Market is unsuitable",
        "ENTRY_UNAVAILABLE": "Entry price unavailable",
        "STOP_UNAVAILABLE": "Stop price unavailable",
        "TARGET_UNAVAILABLE": "Target price unavailable",
        "INVALID_PRICE_GEOMETRY": "Invalid entry, stop and target geometry",
        "STOP_TOO_WIDE": "Stop distance exceeds configured maximum",
        "REWARD_RISK_TOO_LOW": f"Reward/risk below minimum {configuration.minimum_reward_risk:.2f}",
        "CAPITAL_UNAVAILABLE": "Trading capital not configured",
        "RISK_BUDGET_EXHAUSTED": "Risk budget exhausted",
        "LOT_SIZE_UNAVAILABLE": "Instrument lot size unavailable",
        "QUANTITY_BELOW_ONE_LOT": "Calculated quantity is below one lot",
        "DAILY_TRADE_LIMIT": "Daily trade limit reached",
        "DAILY_LOSS_LIMIT": "Daily loss limit reached",
        "POSITION_ALREADY_ACTIVE": "Position already active",
    }
    return messages.get(code, code.replace("_", " ").title())
