"""
Risk Engine V1.
"""

import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from math import floor, isfinite
from numbers import Real
from zoneinfo import ZoneInfo

from core.base_engine import BaseEngine
from core.events import (
    RISK_APPROVED,
    RISK_EMERGENCY_LOCKED,
    RISK_EVALUATED,
    RISK_LOCKED,
    RISK_MANUAL_LOCKED,
    RISK_REJECTED,
    RISK_SESSION_RESET,
    RISK_STATE_UPDATED,
    RISK_UPDATED,
)
from engines.risk.calculator import RiskCalculator
from engines.risk.enums import (
    RiskDecision,
    RiskDecisionStatus,
    RiskLifecycleState,
    RiskReasonCode,
    RiskRejectionReason,
    RiskReductionReason,
    RiskSeverity,
    RiskTier,
)
from engines.risk.models import (
    AccountRiskState,
    RiskDecisionRecord,
    RiskDecisionState,
    RiskEngineSnapshot,
    RiskFinding,
    RiskPolicy,
    RiskSnapshot,
    SessionRiskState,
    TradeRiskPlan,
)
from engines.strategy.enums import (
    BlockReason,
    EntryReference,
    StopReference,
    StrategyDecision,
    TargetReference,
    TradeDirection,
)
from engines.strategy.models import StrategyDecisionState


IST = ZoneInfo("Asia/Kolkata")
SUPPORTED_INSTRUMENTS = {"NIFTY", "BANKNIFTY", "SENSEX"}


class RiskEngine(BaseEngine):
    """
    Pre-order risk approval gate for one symbol and timeframe.

    Risk Engine V1 consumes a Strategy decision, explicit immutable risk
    policy, current account/session risk state, and a numerical trade
    proposal. It does not fetch prices, place orders, connect to a
    broker, estimate margin, account for slippage, brokerage, taxes, or
    Greeks. Monetary risk assumes one price point per unit equals one
    monetary unit. Calls are serialized and single-threaded.
    """

    def __init__(self, event_bus, symbol: str, timeframe: str):
        super().__init__(event_bus)
        self._symbol = self._normalize_symbol(symbol)
        self._timeframe = self._normalize_timeframe(timeframe)
        self._snapshot: RiskSnapshot | None = None
        self._state: RiskDecisionState | None = None
        self._timestamp_is_aware: bool | None = None
        self._lifecycle_state = RiskLifecycleState.CREATED
        today = datetime(2026, 1, 1, 9, 15, tzinfo=IST).date()
        self._session_state = SessionRiskState(today)
        self._last_decision: RiskDecisionRecord | None = None
        self._evaluation_count = 0
        self._approved_count = 0
        self._reduced_size_count = 0
        self._rejected_count = 0
        self._locked_count = 0
        self._policy = RiskPolicy()

    @property
    def snapshot(self) -> RiskSnapshot | None:
        return self._snapshot

    @property
    def state(self) -> RiskDecisionState | None:
        return self._state

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    def start(self) -> RiskEngineSnapshot:
        if self._lifecycle_state is RiskLifecycleState.FAILED:
            raise RuntimeError("RiskEngine cannot start from FAILED state.")
        self._lifecycle_state = RiskLifecycleState.READY
        return self.engine_snapshot()

    def stop(self) -> RiskEngineSnapshot:
        self._lifecycle_state = RiskLifecycleState.STOPPED
        return self.engine_snapshot()

    def evaluate(
        self,
        *,
        policy: RiskPolicy,
        account: AccountRiskState,
        trade_plan: TradeRiskPlan,
        timestamp: datetime | None = None,
    ) -> RiskDecisionRecord:
        if self._lifecycle_state in {RiskLifecycleState.CREATED, RiskLifecycleState.STOPPED}:
            self.start()
        when = self._evaluation_timestamp(timestamp, trade_plan)
        self._roll_session_if_needed(when.date())
        self._policy = policy
        try:
            decision = self._evaluate(policy=policy, account=account, trade_plan=trade_plan, timestamp=when)
        except Exception:
            self._lifecycle_state = RiskLifecycleState.FAILED
            raise
        self._record_authoritative_decision(decision)
        return decision

    def record_trade_opened(
        self,
        *,
        instrument: str,
        risk_amount: float,
        timestamp: datetime,
    ) -> RiskEngineSnapshot:
        when = self._require_aware(timestamp, "timestamp")
        self._roll_session_if_needed(when.date())
        symbol = self._normalize_symbol(instrument)
        amount = self._non_negative_real("risk_amount", risk_amount)
        risk_by_instrument = dict(self._session_state.instrument_open_risk)
        risk_by_instrument[symbol] = round(risk_by_instrument.get(symbol, 0.0) + amount, 2)
        self._session_state = replace(
            self._session_state,
            trades_taken=self._session_state.trades_taken + 1,
            last_trade_timestamp=when,
            last_entry_timestamp=when,
            current_open_risk=round(self._session_state.current_open_risk + amount, 2),
            instrument_open_risk=risk_by_instrument,
        )
        self._event_bus.publish(RISK_STATE_UPDATED, self.engine_snapshot())
        return self.engine_snapshot()

    def record_trade_closed(
        self,
        *,
        instrument: str,
        risk_amount: float = 0.0,
        realized_pnl: float = 0.0,
        timestamp: datetime,
    ) -> RiskEngineSnapshot:
        when = self._require_aware(timestamp, "timestamp")
        self._roll_session_if_needed(when.date())
        symbol = self._normalize_symbol(instrument)
        amount = self._non_negative_real("risk_amount", risk_amount)
        pnl = self._finite_real("realized_pnl", realized_pnl)
        risk_by_instrument = dict(self._session_state.instrument_open_risk)
        risk_by_instrument[symbol] = round(max(0.0, risk_by_instrument.get(symbol, 0.0) - amount), 2)
        if risk_by_instrument[symbol] == 0:
            risk_by_instrument.pop(symbol)
        wins = self._session_state.winning_trades + (1 if pnl > 0 else 0)
        losses = self._session_state.losing_trades + (1 if pnl < 0 else 0)
        consecutive = 0 if pnl > 0 else self._session_state.consecutive_losses + (1 if pnl < 0 else 0)
        cooldown_until = self._session_state.cooldown_until
        revenge_until = self._session_state.revenge_lock_until
        if pnl < 0:
            cooldown_until = when + timedelta(minutes=max(self._policy.cooldown_minutes_after_loss, 0))
            revenge_until = when + timedelta(minutes=max(self._policy.revenge_trade_window_minutes, 0))
        self._session_state = replace(
            self._session_state,
            winning_trades=wins,
            losing_trades=losses,
            consecutive_losses=consecutive,
            last_trade_timestamp=when,
            last_loss_timestamp=when if pnl < 0 else self._session_state.last_loss_timestamp,
            realized_pnl=round(self._session_state.realized_pnl + pnl, 2),
            current_open_risk=round(max(0.0, self._session_state.current_open_risk - amount), 2),
            instrument_open_risk=risk_by_instrument,
            cooldown_until=cooldown_until,
            revenge_lock_until=revenge_until,
        )
        self._event_bus.publish(RISK_STATE_UPDATED, self.engine_snapshot())
        return self.engine_snapshot()

    def record_loss(self, *, amount: float = 0.0, timestamp: datetime) -> RiskEngineSnapshot:
        return self.record_trade_closed(instrument=self._symbol, realized_pnl=-abs(float(amount)), timestamp=timestamp)

    def record_win(self, *, amount: float = 0.0, timestamp: datetime) -> RiskEngineSnapshot:
        return self.record_trade_closed(instrument=self._symbol, realized_pnl=abs(float(amount)), timestamp=timestamp)

    def activate_manual_lock(self, reason: str = "Manual risk lock activated.") -> RiskEngineSnapshot:
        self._session_state = replace(self._session_state, manual_lock_active=True)
        self._lifecycle_state = RiskLifecycleState.LOCKED
        self._event_bus.publish(RISK_MANUAL_LOCKED, self.engine_snapshot())
        return self.engine_snapshot()

    def activate_emergency_lock(self, reason: str = "Emergency risk lock activated.") -> RiskEngineSnapshot:
        self._session_state = replace(self._session_state, emergency_lock_active=True)
        self._lifecycle_state = RiskLifecycleState.LOCKED
        self._event_bus.publish(RISK_EMERGENCY_LOCKED, self.engine_snapshot())
        return self.engine_snapshot()

    def clear_manual_lock(self) -> RiskEngineSnapshot:
        self._session_state = replace(self._session_state, manual_lock_active=False)
        if not self._session_state.emergency_lock_active:
            self._lifecycle_state = RiskLifecycleState.READY
        self._event_bus.publish(RISK_STATE_UPDATED, self.engine_snapshot())
        return self.engine_snapshot()

    def reset_session(self, trading_date: date) -> RiskEngineSnapshot:
        if isinstance(trading_date, datetime) or not isinstance(trading_date, date):
            raise TypeError("trading_date must be a date")
        emergency = self._session_state.emergency_lock_active
        self._session_state = SessionRiskState(trading_date, emergency_lock_active=emergency)
        self._last_decision = None
        self._state = None
        self._data = None
        self._lifecycle_state = RiskLifecycleState.LOCKED if emergency else RiskLifecycleState.READY
        self._event_bus.publish(RISK_SESSION_RESET, self.engine_snapshot())
        return self.engine_snapshot()

    def engine_snapshot(self) -> RiskEngineSnapshot:
        daily_pnl = round(self._session_state.realized_pnl + self._session_state.unrealized_pnl, 2)
        return RiskEngineSnapshot(
            enabled=self._policy.enabled,
            lifecycle_state=self._lifecycle_state,
            trading_date=self._session_state.trading_date,
            manual_lock_active=self._session_state.manual_lock_active,
            emergency_lock_active=self._session_state.emergency_lock_active,
            daily_profit_lock_active=self._session_state.daily_profit_lock_active,
            trades_taken=self._session_state.trades_taken,
            winning_trades=self._session_state.winning_trades,
            losing_trades=self._session_state.losing_trades,
            consecutive_losses=self._session_state.consecutive_losses,
            realized_pnl=self._session_state.realized_pnl,
            unrealized_pnl=self._session_state.unrealized_pnl,
            daily_pnl=daily_pnl,
            current_open_risk=self._session_state.current_open_risk,
            instrument_open_risk=dict(self._session_state.instrument_open_risk),
            cooldown_until=self._session_state.cooldown_until,
            revenge_lock_until=self._session_state.revenge_lock_until,
            last_decision=self._last_decision,
            findings=self._session_state.findings,
            evaluation_count=self._evaluation_count,
            approved_count=self._approved_count,
            reduced_size_count=self._reduced_size_count,
            rejected_count=self._rejected_count,
            locked_count=self._locked_count,
            broker_order_calls=0,
        )

    def _evaluate(
        self,
        *,
        policy: RiskPolicy,
        account: AccountRiskState,
        trade_plan: TradeRiskPlan,
        timestamp: datetime,
    ) -> RiskDecisionRecord:
        policy = self._validate_authoritative_policy(policy)
        account_values = self._validate_authoritative_account(account, timestamp)
        plan_values = self._validate_authoritative_plan(trade_plan, timestamp)
        findings: list[RiskFinding] = []

        def add(severity, code, message, field_name=None, observed_value=None, limit_value=None):
            findings.append(
                self._finding(
                    timestamp,
                    severity,
                    code,
                    message,
                    field_name=field_name,
                    observed_value=observed_value,
                    limit_value=limit_value,
                )
            )

        instrument = plan_values["instrument"]
        direction = plan_values["direction"]
        entry = plan_values["entry"]
        stop = plan_values["stop"]
        target = plan_values["target"]
        lot_size = plan_values["lot_size"]
        requested_lots = plan_values["requested_lots"]
        requested_quantity = plan_values["requested_quantity"]
        configured_lot_size = policy.lot_sizes_by_instrument.get(instrument)
        if configured_lot_size is not None:
            lot_size = configured_lot_size
            if trade_plan.requested_quantity is None:
                requested_quantity = requested_lots * lot_size

        if not policy.enabled:
            add(RiskSeverity.ERROR, RiskReasonCode.INVALID_PLAN, "Risk policy is disabled.", "enabled", "False", "True")
            return self._decision(timestamp, policy, trade_plan, RiskDecisionStatus.INVALID, False, instrument, direction, requested_quantity, 0, requested_lots, 0, entry, stop, target, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, RiskReasonCode.INVALID_PLAN, findings)
        if self._session_state.emergency_lock_active:
            add(RiskSeverity.CRITICAL, RiskReasonCode.EMERGENCY_LOCK_ACTIVE, "Emergency risk lock is active.")
            return self._locked_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.EMERGENCY_LOCK_ACTIVE, findings)
        if self._session_state.manual_lock_active:
            add(RiskSeverity.ERROR, RiskReasonCode.MANUAL_LOCK_ACTIVE, "Manual risk lock is active.")
            return self._locked_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.MANUAL_LOCK_ACTIVE, findings)
        if instrument not in SUPPORTED_INSTRUMENTS:
            add(RiskSeverity.ERROR, RiskReasonCode.UNSUPPORTED_INSTRUMENT, "Unsupported instrument.", "instrument", instrument, ",".join(sorted(SUPPORTED_INSTRUMENTS)))
            return self._invalid_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.UNSUPPORTED_INSTRUMENT, findings)
        if account_values["session_date"] != timestamp.astimezone(IST).date():
            add(RiskSeverity.ERROR, RiskReasonCode.OUTSIDE_TRADING_WINDOW, "Account session date does not match evaluation date.", "session_date", str(account_values["session_date"]), str(timestamp.astimezone(IST).date()))
            return self._invalid_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.OUTSIDE_TRADING_WINDOW, findings)
        if timestamp.astimezone(IST).time() < policy.trading_start_time or timestamp.astimezone(IST).time() > policy.last_entry_time:
            code = RiskReasonCode.LATE_ENTRY if timestamp.astimezone(IST).time() > policy.last_entry_time else RiskReasonCode.OUTSIDE_TRADING_WINDOW
            add(RiskSeverity.ERROR, code, "Trade timestamp is outside the allowed entry window.", "timestamp", timestamp.astimezone(IST).time().isoformat(), f"{policy.trading_start_time.isoformat()}-{policy.last_entry_time.isoformat()}")
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, code, findings)
        if account_values["available_capital"] <= 0:
            add(RiskSeverity.ERROR, RiskReasonCode.INSUFFICIENT_CAPITAL, "No available capital is present.", "available_capital", str(account_values["available_capital"]), ">0")
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.INSUFFICIENT_CAPITAL, findings)
        loss_limit = self._daily_loss_limit(policy, account_values["available_capital"])
        if loss_limit is not None and max(-account_values["daily_pnl"], 0.0) >= loss_limit:
            add(RiskSeverity.CRITICAL, RiskReasonCode.DAILY_LOSS_LIMIT_REACHED, "Daily loss limit reached.", "daily_pnl", str(account_values["daily_pnl"]), str(-loss_limit))
            return self._locked_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.DAILY_LOSS_LIMIT_REACHED, findings)
        if self._profit_lock_triggered(policy, account_values["daily_pnl"]):
            add(RiskSeverity.ERROR, RiskReasonCode.DAILY_PROFIT_LOCK_ACTIVE, "Daily profit protection lock is active.")
            return self._locked_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.DAILY_PROFIT_LOCK_ACTIVE, findings)
        if self._session_state.trades_taken >= policy.maximum_trades_per_session:
            add(RiskSeverity.ERROR, RiskReasonCode.MAX_TRADES_REACHED, "Maximum trades per session reached.", "trades_taken", str(self._session_state.trades_taken), str(policy.maximum_trades_per_session))
            return self._locked_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.MAX_TRADES_REACHED, findings)
        if self._session_state.cooldown_until is not None and timestamp < self._session_state.cooldown_until:
            add(RiskSeverity.ERROR, RiskReasonCode.CONSECUTIVE_LOSS_COOLDOWN, "Consecutive-loss cooldown is active.", "cooldown_until", self._session_state.cooldown_until.isoformat(), timestamp.isoformat())
            return self._locked_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.CONSECUTIVE_LOSS_COOLDOWN, findings)
        if self._session_state.revenge_lock_until is not None and timestamp < self._session_state.revenge_lock_until and (trade_plan.is_revenge_entry or trade_plan.is_fomo_entry):
            add(RiskSeverity.ERROR, RiskReasonCode.REVENGE_TRADING_LOCKOUT, "Revenge-trading lockout is active.")
            return self._locked_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.REVENGE_TRADING_LOCKOUT, findings)
        if trade_plan.is_fomo_entry and not policy.allow_fomo_entry:
            add(RiskSeverity.ERROR, RiskReasonCode.FOMO_ENTRY, "FOMO entry is blocked by risk policy.")
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.FOMO_ENTRY, findings)
        if trade_plan.is_averaging_entry and not policy.allow_averaging_down:
            add(RiskSeverity.ERROR, RiskReasonCode.AVERAGING_DOWN_BLOCKED, "Averaging down is blocked by risk policy.")
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.AVERAGING_DOWN_BLOCKED, findings)
        existing_qty = self._non_negative_int_value("existing_position_quantity", trade_plan.existing_position_quantity)
        existing_direction = self._normalize_optional_direction(trade_plan.existing_position_direction)
        if existing_qty > 0 and existing_direction is direction and not policy.allow_duplicate_direction:
            add(RiskSeverity.ERROR, RiskReasonCode.DUPLICATE_POSITION, "Duplicate same-direction exposure is blocked.")
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.DUPLICATE_POSITION, findings)
        if stop is None and policy.require_stop_loss:
            add(RiskSeverity.ERROR, RiskReasonCode.MISSING_STOP_LOSS, "Stop-loss is required.")
            return self._invalid_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.MISSING_STOP_LOSS, findings)
        if target is None and policy.require_target:
            add(RiskSeverity.ERROR, RiskReasonCode.MISSING_TARGET, "Target is required.")
            return self._invalid_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.MISSING_TARGET, findings)

        geometry = self._risk_geometry(direction, entry, stop, target)
        if geometry is None:
            add(RiskSeverity.ERROR, RiskReasonCode.INVALID_STOP, "Invalid directional entry, stop or target placement.")
            return self._invalid_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.INVALID_STOP, findings)
        risk_per_unit, reward_per_unit, reward_to_risk = geometry
        stop_pct = risk_per_unit / entry * 100
        if policy.minimum_stop_distance_percentage is not None and stop_pct < policy.minimum_stop_distance_percentage:
            add(RiskSeverity.ERROR, RiskReasonCode.STOP_TOO_TIGHT, "Stop distance is below policy minimum.", "stop_distance_percentage", f"{stop_pct:.4f}", str(policy.minimum_stop_distance_percentage))
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.STOP_TOO_TIGHT, findings)
        if policy.maximum_stop_distance_percentage is not None and stop_pct > policy.maximum_stop_distance_percentage:
            add(RiskSeverity.ERROR, RiskReasonCode.STOP_TOO_WIDE, "Stop distance exceeds policy maximum.", "stop_distance_percentage", f"{stop_pct:.4f}", str(policy.maximum_stop_distance_percentage))
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.STOP_TOO_WIDE, findings)
        if reward_to_risk < policy.minimum_reward_to_risk:
            add(RiskSeverity.ERROR, RiskReasonCode.INSUFFICIENT_REWARD_RISK, "Reward-to-risk is below policy minimum.", "reward_to_risk", f"{reward_to_risk:.4f}", str(policy.minimum_reward_to_risk))
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.INSUFFICIENT_REWARD_RISK, findings)

        minimum_lot_risk = lot_size * risk_per_unit
        if policy.maximum_instrument_open_risk is not None:
            used = self._session_state.instrument_open_risk.get(instrument, 0.0)
            if used + minimum_lot_risk > policy.maximum_instrument_open_risk:
                add(RiskSeverity.ERROR, RiskReasonCode.INSTRUMENT_EXPOSURE_EXCEEDED, "Instrument open risk limit exceeded.", "instrument_open_risk_after_trade", str(round(used + minimum_lot_risk, 2)), str(policy.maximum_instrument_open_risk))
                return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.INSTRUMENT_EXPOSURE_EXCEEDED, findings)
        if policy.maximum_total_open_risk is not None and self._session_state.current_open_risk + minimum_lot_risk > policy.maximum_total_open_risk:
            add(RiskSeverity.ERROR, RiskReasonCode.TOTAL_OPEN_RISK_EXCEEDED, "Total open risk limit exceeded.", "total_open_risk_after_trade", str(round(self._session_state.current_open_risk + minimum_lot_risk, 2)), str(policy.maximum_total_open_risk))
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.TOTAL_OPEN_RISK_EXCEEDED, findings)

        maximum_allowed_trade_risk = self._maximum_allowed_trade_risk(policy, account_values, instrument)
        if maximum_allowed_trade_risk <= 0 or account_values["available_capital"] <= 0:
            add(RiskSeverity.ERROR, RiskReasonCode.INSUFFICIENT_CAPITAL, "No risk capacity is available.")
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.INSUFFICIENT_CAPITAL, findings)
        allowed_by_risk = floor(maximum_allowed_trade_risk / risk_per_unit)
        allowed_by_lots = policy.maximum_lots * lot_size
        allowed_by_quantity = policy.maximum_quantity if policy.maximum_quantity is not None else requested_quantity
        allowed_quantity = min(requested_quantity, allowed_by_risk, allowed_by_lots, allowed_by_quantity)
        approved_lots = floor(allowed_quantity / lot_size)
        approved_quantity = approved_lots * lot_size
        primary = RiskReasonCode.APPROVED
        status = RiskDecisionStatus.APPROVED
        if requested_quantity > min(allowed_by_risk, allowed_by_lots, allowed_by_quantity):
            primary = RiskReasonCode.SIZE_REDUCED
            status = RiskDecisionStatus.APPROVED_WITH_REDUCED_SIZE
            add(RiskSeverity.WARNING, primary, "Requested size reduced to policy-compliant quantity.", "requested_quantity", str(requested_quantity), str(approved_quantity))
        if approved_quantity <= 0:
            code = RiskReasonCode.MAX_LOTS_EXCEEDED if allowed_by_lots <= 0 else RiskReasonCode.RISK_PER_TRADE_EXCEEDED
            add(RiskSeverity.ERROR, code, "No valid positive lot multiple remains after risk limits.")
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, code, findings)

        approved_risk = round(approved_quantity * risk_per_unit, 2)
        requested_risk = round(requested_quantity * risk_per_unit, 2)
        estimated_reward = round(approved_quantity * reward_per_unit, 2)
        total_after = round(self._session_state.current_open_risk + approved_risk, 2)
        instrument_after = round(self._session_state.instrument_open_risk.get(instrument, 0.0) + approved_risk, 2)
        if policy.maximum_total_open_risk is not None and total_after > policy.maximum_total_open_risk:
            add(RiskSeverity.ERROR, RiskReasonCode.TOTAL_OPEN_RISK_EXCEEDED, "Total open risk limit exceeded.", "total_open_risk_after_trade", str(total_after), str(policy.maximum_total_open_risk))
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.TOTAL_OPEN_RISK_EXCEEDED, findings)
        if policy.maximum_instrument_open_risk is not None and instrument_after > policy.maximum_instrument_open_risk:
            add(RiskSeverity.ERROR, RiskReasonCode.INSTRUMENT_EXPOSURE_EXCEEDED, "Instrument open risk limit exceeded.", "instrument_open_risk_after_trade", str(instrument_after), str(policy.maximum_instrument_open_risk))
            return self._rejected_decision(timestamp, policy, trade_plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, RiskReasonCode.INSTRUMENT_EXPOSURE_EXCEEDED, findings)
        if status is RiskDecisionStatus.APPROVED:
            add(RiskSeverity.INFO, RiskReasonCode.APPROVED, "Risk approved.")
        return self._decision(
            timestamp,
            policy,
            trade_plan,
            status,
            True,
            instrument,
            direction,
            requested_quantity,
            approved_quantity,
            requested_lots,
            approved_lots,
            entry,
            stop,
            target,
            risk_per_unit,
            reward_per_unit,
            reward_to_risk,
            requested_risk,
            approved_risk,
            maximum_allowed_trade_risk,
            estimated_reward,
            round((approved_risk / account_values["available_capital"]) * 100, 4),
            total_after,
            instrument_after,
            primary,
            findings,
        )

    def _locked_decision(self, timestamp, policy, plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, code, findings):
        return self._decision(timestamp, policy, plan, RiskDecisionStatus.LOCKED, False, instrument, direction, requested_quantity, 0, requested_lots, 0, entry, stop, target, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, code, findings)

    def _invalid_decision(self, timestamp, policy, plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, code, findings):
        return self._decision(timestamp, policy, plan, RiskDecisionStatus.INVALID, False, instrument, direction, requested_quantity, 0, requested_lots, 0, entry, stop, target, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, code, findings)

    def _rejected_decision(self, timestamp, policy, plan, instrument, direction, requested_quantity, requested_lots, entry, stop, target, code, findings):
        return self._decision(timestamp, policy, plan, RiskDecisionStatus.REJECTED, False, instrument, direction, requested_quantity, 0, requested_lots, 0, entry, stop, target, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, code, findings)

    def _decision(
        self,
        timestamp,
        policy,
        plan,
        status,
        approved,
        instrument,
        direction,
        requested_quantity,
        approved_quantity,
        requested_lots,
        approved_lots,
        entry,
        stop,
        target,
        risk_per_unit,
        reward_per_unit,
        reward_to_risk,
        requested_trade_risk,
        approved_trade_risk,
        maximum_allowed_trade_risk,
        estimated_reward,
        capital_at_risk_percentage,
        total_open_risk_after_trade,
        instrument_open_risk_after_trade,
        primary_reason,
        findings,
    ):
        policy_fingerprint = policy.fingerprint()
        plan_fingerprint = plan.fingerprint()
        input_fingerprint = _stable_hash(
            {
                "policy": policy_fingerprint,
                "plan": plan_fingerprint,
                "session": self._session_payload(),
                "timestamp": timestamp.isoformat(),
            }
        )
        normalized_findings = self._dedupe_findings(findings, timestamp)
        decision_id = _stable_hash({"input": input_fingerprint, "reason": primary_reason.value})[:16]
        return RiskDecisionRecord(
            decision_id=decision_id,
            timestamp=timestamp,
            status=status,
            approved=approved,
            instrument=instrument,
            direction=direction,
            requested_quantity=requested_quantity,
            approved_quantity=approved_quantity,
            requested_lots=requested_lots,
            approved_lots=approved_lots,
            entry_price=round(entry, 4),
            stop_loss_price=round(stop, 4) if stop is not None else None,
            target_price=round(target, 4) if target is not None else None,
            risk_per_unit=round(risk_per_unit, 4),
            reward_per_unit=round(reward_per_unit, 4),
            reward_to_risk=round(reward_to_risk, 4),
            requested_trade_risk=round(requested_trade_risk, 2),
            approved_trade_risk=round(approved_trade_risk, 2),
            maximum_allowed_trade_risk=round(maximum_allowed_trade_risk, 2),
            estimated_reward=round(estimated_reward, 2),
            capital_at_risk_percentage=round(capital_at_risk_percentage, 4),
            total_open_risk_after_trade=round(total_open_risk_after_trade, 2),
            instrument_open_risk_after_trade=round(instrument_open_risk_after_trade, 2),
            primary_reason=primary_reason,
            findings=normalized_findings,
            manual_approval_required=policy.manual_approval_required and not plan.manual_approval,
            policy_fingerprint=policy_fingerprint,
            plan_fingerprint=plan_fingerprint,
            input_fingerprint=input_fingerprint,
        )

    def _record_authoritative_decision(self, decision: RiskDecisionRecord) -> None:
        self._last_decision = decision
        self._evaluation_count += 1
        if decision.status is RiskDecisionStatus.APPROVED:
            self._approved_count += 1
            event = RISK_APPROVED
            self._lifecycle_state = RiskLifecycleState.ACTIVE
        elif decision.status is RiskDecisionStatus.APPROVED_WITH_REDUCED_SIZE:
            self._approved_count += 1
            self._reduced_size_count += 1
            event = RISK_APPROVED
            self._lifecycle_state = RiskLifecycleState.ACTIVE
        elif decision.status is RiskDecisionStatus.LOCKED:
            self._locked_count += 1
            event = RISK_LOCKED
            self._lifecycle_state = RiskLifecycleState.LOCKED
        else:
            self._rejected_count += 1
            event = RISK_REJECTED
            if self._lifecycle_state is RiskLifecycleState.CREATED:
                self._lifecycle_state = RiskLifecycleState.READY
        self._session_state = replace(
            self._session_state,
            findings=self._merge_session_findings(decision.findings),
            daily_profit_lock_active=self._session_state.daily_profit_lock_active
            or decision.primary_reason is RiskReasonCode.DAILY_PROFIT_LOCK_ACTIVE,
        )
        self._state = self._legacy_state_from_decision(decision)
        self._data = self._state
        self._event_bus.publish(RISK_EVALUATED, decision)
        self._event_bus.publish(event, decision)
        self._event_bus.publish(RISK_UPDATED, self._state)
        self._event_bus.publish(RISK_STATE_UPDATED, self.engine_snapshot())

    def update(self, snapshot: RiskSnapshot) -> RiskDecisionState:
        canonical = self._canonicalize_snapshot(snapshot)

        if self._snapshot is not None:
            if canonical.timestamp < self._snapshot.timestamp:
                raise ValueError(
                    "Stale RiskSnapshot received: "
                    f"{canonical.timestamp.isoformat()} < {self._snapshot.timestamp.isoformat()}"
                )
            if canonical == self._snapshot:
                return self._state

        state = RiskCalculator.calculate(canonical)
        self._snapshot = canonical
        self._state = state
        self._data = state
        self._event_bus.publish(RISK_UPDATED, state)
        return state

    def process(self, snapshot: RiskSnapshot) -> RiskDecisionState:
        """
        Alias for update().
        """
        return self.update(snapshot)

    def record_decision(self, state: RiskDecisionState) -> RiskDecisionState:
        if not isinstance(state, RiskDecisionState):
            raise TypeError("state must be RiskDecisionState")
        if self._normalize_symbol(state.symbol) != self._symbol:
            raise ValueError("RiskDecisionState symbol does not match risk context.")
        if self._normalize_timeframe(state.timeframe) != self._timeframe:
            raise ValueError("RiskDecisionState timeframe does not match risk context.")
        self._state = state
        self._data = state
        self._event_bus.publish(RISK_UPDATED, state)
        return state

    def reset(self) -> None:
        super().clear()
        self._snapshot = None
        self._state = None
        self._timestamp_is_aware = None
        emergency = self._session_state.emergency_lock_active
        self._session_state = SessionRiskState(self._session_state.trading_date, emergency_lock_active=emergency)
        self._last_decision = None
        self._evaluation_count = 0
        self._approved_count = 0
        self._reduced_size_count = 0
        self._rejected_count = 0
        self._locked_count = 0
        self._lifecycle_state = RiskLifecycleState.LOCKED if emergency else RiskLifecycleState.CREATED

    def clear(self) -> None:
        self.reset()

    def _validate_authoritative_policy(self, policy: RiskPolicy) -> RiskPolicy:
        if not isinstance(policy, RiskPolicy):
            raise ValueError("policy must be a RiskPolicy.")
        if type(policy.enabled) is not bool:
            raise TypeError("enabled must be bool")
        self._percentage_like("risk_per_trade_percentage", policy.risk_per_trade_percentage)
        if policy.maximum_risk_per_trade_amount is not None:
            self._positive_real("maximum_risk_per_trade_amount", policy.maximum_risk_per_trade_amount)
        if policy.maximum_daily_loss_amount is not None:
            self._positive_real("maximum_daily_loss_amount", policy.maximum_daily_loss_amount)
        if policy.maximum_daily_loss_percentage is not None:
            self._percentage_like("maximum_daily_loss_percentage", policy.maximum_daily_loss_percentage)
        if policy.daily_profit_lock_trigger is not None:
            self._positive_real("daily_profit_lock_trigger", policy.daily_profit_lock_trigger)
        if policy.daily_profit_giveback_limit is not None:
            self._non_negative_real("daily_profit_giveback_limit", policy.daily_profit_giveback_limit)
        for name in ("maximum_trades_per_session", "maximum_consecutive_losses", "maximum_lots"):
            self._positive_int(name, getattr(policy, name))
        for name in ("cooldown_minutes_after_loss", "revenge_trade_window_minutes"):
            self._non_negative_int(name, getattr(policy, name))
        self._positive_real("minimum_reward_to_risk", policy.minimum_reward_to_risk)
        for name in ("maximum_stop_distance_percentage", "minimum_stop_distance_percentage"):
            value = getattr(policy, name)
            if value is not None:
                self._positive_real(name, value)
        for name in ("maximum_total_open_risk", "maximum_instrument_open_risk"):
            value = getattr(policy, name)
            if value is not None:
                self._positive_real(name, value)
        if policy.maximum_quantity is not None:
            self._positive_int("maximum_quantity", policy.maximum_quantity)
        if not isinstance(policy.lot_sizes_by_instrument, dict) or not policy.lot_sizes_by_instrument:
            raise ValueError("lot_sizes_by_instrument must be a non-empty mapping.")
        for symbol, lot_size in policy.lot_sizes_by_instrument.items():
            self._normalize_symbol(symbol)
            self._positive_int("lot_size", lot_size)
        for name in ("allow_averaging_down", "allow_duplicate_direction", "allow_fomo_entry", "require_stop_loss", "require_target", "manual_approval_required"):
            if type(getattr(policy, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        for name in ("trading_start_time", "last_entry_time", "force_exit_time"):
            if not isinstance(getattr(policy, name), time):
                raise TypeError(f"{name} must be a time")
        if policy.trading_start_time >= policy.last_entry_time:
            raise ValueError("trading_start_time must be before last_entry_time")
        return policy

    def _validate_authoritative_account(self, account: AccountRiskState, timestamp: datetime) -> dict[str, float | date]:
        if not isinstance(account, AccountRiskState):
            raise ValueError("account must be an AccountRiskState.")
        starting = self._resolve_number(account.starting_capital, account.account_equity, "starting_capital")
        available = self._resolve_number(account.available_capital, account.account_equity, "available_capital")
        realized = self._resolve_number(account.realized_pnl, account.realized_pnl_today, "realized_pnl")
        unrealized = self._finite_real("unrealized_pnl", account.unrealized_pnl)
        daily = self._resolve_number(account.daily_pnl, realized + unrealized, "daily_pnl")
        open_risk = self._non_negative_real("open_risk", account.open_risk)
        margin = self._non_negative_real("margin_used", account.margin_used)
        if starting < 0 or available < 0:
            raise ValueError("capital cannot be negative")
        session_date = account.session_date or timestamp.astimezone(IST).date()
        if isinstance(session_date, datetime) or not isinstance(session_date, date):
            raise TypeError("session_date must be a date")
        return {
            "starting_capital": starting,
            "available_capital": available,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "daily_pnl": daily,
            "open_risk": open_risk,
            "margin_used": margin,
            "session_date": session_date,
        }

    def _validate_authoritative_plan(self, plan: TradeRiskPlan, timestamp: datetime) -> dict:
        if not isinstance(plan, TradeRiskPlan):
            raise ValueError("trade_plan must be a TradeRiskPlan.")
        instrument = self._normalize_symbol(plan.instrument)
        direction = self._normalize_direction(plan.direction)
        entry = self._positive_real("entry_price", plan.entry_price)
        stop = self._optional_positive_real("stop_loss_price", plan.effective_stop_loss_price)
        target = self._optional_positive_real("target_price", plan.effective_target_price)
        lot_size = self._positive_int("lot_size", plan.lot_size)
        requested_lots = self._positive_int("requested_lots", plan.requested_lots)
        requested_quantity = plan.requested_quantity
        if requested_quantity is None:
            requested_quantity = requested_lots * lot_size
        requested_quantity = self._positive_int("requested_quantity", requested_quantity)
        if requested_quantity < lot_size:
            raise ValueError("requested_quantity must be at least one lot")
        if plan.timestamp is not None:
            self._require_aware(plan.timestamp, "trade_plan.timestamp")
            if plan.timestamp != timestamp:
                raise ValueError("trade_plan timestamp must match evaluation timestamp")
        for name in ("is_retest_entry", "is_fomo_entry", "is_averaging_entry", "is_revenge_entry", "manual_approval"):
            if type(getattr(plan, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        return {
            "instrument": instrument,
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "target": target,
            "lot_size": lot_size,
            "requested_lots": requested_lots,
            "requested_quantity": requested_quantity,
        }

    def _evaluation_timestamp(self, timestamp: datetime | None, plan: TradeRiskPlan) -> datetime:
        value = timestamp if timestamp is not None else plan.timestamp
        return self._require_aware(value, "timestamp")

    def _roll_session_if_needed(self, trading_date: date) -> None:
        if self._session_state.trading_date != trading_date:
            emergency = self._session_state.emergency_lock_active
            manual = self._session_state.manual_lock_active
            self._session_state = SessionRiskState(
                trading_date,
                manual_lock_active=manual,
                emergency_lock_active=emergency,
            )

    def _profit_lock_triggered(self, policy: RiskPolicy, daily_pnl: float) -> bool:
        if policy.daily_profit_lock_trigger is None or policy.daily_profit_giveback_limit is None:
            return self._session_state.daily_profit_lock_active
        peak = max(self._session_state.peak_daily_profit, daily_pnl)
        active = self._session_state.daily_profit_lock_active or peak >= policy.daily_profit_lock_trigger
        locked = active and daily_pnl <= peak - policy.daily_profit_giveback_limit
        self._session_state = replace(self._session_state, peak_daily_profit=peak, daily_profit_lock_active=active or locked)
        return locked

    def _daily_loss_limit(self, policy: RiskPolicy, available_capital: float) -> float | None:
        limits = []
        if policy.maximum_daily_loss_amount is not None:
            limits.append(policy.maximum_daily_loss_amount)
        if policy.maximum_daily_loss_percentage is not None:
            limits.append(available_capital * policy.maximum_daily_loss_percentage / 100)
        return min(limits) if limits else None

    def _maximum_allowed_trade_risk(self, policy: RiskPolicy, account: dict, instrument: str) -> float:
        limits = [account["available_capital"] * policy.risk_per_trade_percentage / 100]
        if policy.maximum_risk_per_trade_amount is not None:
            limits.append(policy.maximum_risk_per_trade_amount)
        daily_limit = self._daily_loss_limit(policy, account["available_capital"])
        if daily_limit is not None:
            limits.append(max(0.0, daily_limit + min(account["daily_pnl"], 0.0)))
        if policy.maximum_total_open_risk is not None:
            limits.append(max(0.0, policy.maximum_total_open_risk - self._session_state.current_open_risk))
        if policy.maximum_instrument_open_risk is not None:
            used = self._session_state.instrument_open_risk.get(instrument, 0.0)
            limits.append(max(0.0, policy.maximum_instrument_open_risk - used))
        positive = [float(limit) for limit in limits if limit is not None]
        return round(max(0.0, min(positive)), 2) if positive else 0.0

    def _risk_geometry(self, direction: TradeDirection, entry: float, stop: float | None, target: float | None):
        if stop is None or target is None:
            return None
        if direction is TradeDirection.BULLISH and stop < entry < target:
            risk = entry - stop
            reward = target - entry
            return risk, reward, reward / risk
        if direction is TradeDirection.BEARISH and target < entry < stop:
            risk = stop - entry
            reward = entry - target
            return risk, reward, reward / risk
        return None

    def _legacy_state_from_decision(self, decision: RiskDecisionRecord) -> RiskDecisionState:
        approved = decision.status in {RiskDecisionStatus.APPROVED, RiskDecisionStatus.APPROVED_WITH_REDUCED_SIZE}
        rejection = RiskRejectionReason.NONE if approved else self._legacy_rejection_from_reason(decision.primary_reason)
        return RiskDecisionState(
            symbol=decision.instrument,
            timeframe=self._timeframe,
            timestamp=decision.timestamp,
            decision=RiskDecision.APPROVED if approved else RiskDecision.REJECTED,
            risk_tier=RiskTier.REDUCED if decision.status is RiskDecisionStatus.APPROVED_WITH_REDUCED_SIZE else (RiskTier.STANDARD if approved else RiskTier.BLOCKED),
            rejection_reason=rejection,
            reduction_reason=RiskReductionReason.NONE,
            direction=decision.direction,
            account_equity=0.0,
            realized_pnl_today=self._session_state.realized_pnl,
            daily_loss_limit_amount=0.0,
            remaining_daily_loss_capacity=0.0,
            applied_risk_percent=self._policy.risk_per_trade_percentage,
            risk_budget=decision.maximum_allowed_trade_risk,
            entry_price=decision.entry_price,
            stop_price=decision.stop_loss_price or 0.0,
            target_price=decision.target_price or 0.0,
            stop_distance=decision.risk_per_unit,
            target_distance=decision.reward_per_unit,
            reward_risk_ratio=decision.reward_to_risk,
            lot_size=max(1, int(decision.requested_quantity / decision.requested_lots)) if decision.requested_lots else 0,
            requested_lots=decision.requested_lots,
            maximum_permitted_lots=max(decision.approved_lots, 0),
            approved_lots=decision.approved_lots,
            approved_quantity=decision.approved_quantity,
            estimated_risk_amount=decision.approved_trade_risk,
            estimated_reward_amount=decision.estimated_reward,
            rationale=tuple(f"{item.code.value}:{item.message}" for item in decision.findings),
            risk_reason=decision.primary_reason.value,
            trade_plan_ready=approved,
        )

    def _legacy_rejection_from_reason(self, reason: RiskReasonCode) -> RiskRejectionReason:
        mapping = {
            RiskReasonCode.INSUFFICIENT_REWARD_RISK: RiskRejectionReason.REWARD_RISK_BELOW_MINIMUM,
            RiskReasonCode.DAILY_LOSS_LIMIT_REACHED: RiskRejectionReason.DAILY_LOSS_LIMIT_REACHED,
            RiskReasonCode.MAX_TRADES_REACHED: RiskRejectionReason.DAILY_TRADE_LIMIT_REACHED,
            RiskReasonCode.CONSECUTIVE_LOSS_COOLDOWN: RiskRejectionReason.CONSECUTIVE_LOSS_LIMIT_REACHED,
            RiskReasonCode.INVALID_STOP: RiskRejectionReason.INVALID_PRICE_STRUCTURE,
            RiskReasonCode.MISSING_STOP_LOSS: RiskRejectionReason.INVALID_PRICE_STRUCTURE,
            RiskReasonCode.MISSING_TARGET: RiskRejectionReason.INVALID_PRICE_STRUCTURE,
            RiskReasonCode.INVALID_ENTRY_PRICE: RiskRejectionReason.INVALID_PRICE_STRUCTURE,
            RiskReasonCode.INVALID_QUANTITY: RiskRejectionReason.REQUESTED_SIZE_EXCEEDS_LIMIT,
        }
        return mapping.get(reason, RiskRejectionReason.INSUFFICIENT_RISK_BUDGET)

    def _finding(self, timestamp, severity, code, message, *, field_name=None, observed_value=None, limit_value=None):
        finding_id = _stable_hash({"timestamp": timestamp.isoformat(), "code": code.value, "field": field_name or ""})[:16]
        return RiskFinding(
            finding_id=finding_id,
            timestamp=timestamp,
            severity=severity,
            code=code,
            message=message,
            field_name=field_name,
            observed_value=None if observed_value is None else str(observed_value)[:200],
            limit_value=None if limit_value is None else str(limit_value)[:200],
        )

    def _dedupe_findings(self, findings: list[RiskFinding], timestamp: datetime) -> tuple[RiskFinding, ...]:
        ordered = []
        by_code = {}
        for finding in findings:
            if finding.code in by_code:
                current = by_code[finding.code]
                by_code[finding.code] = replace(current, occurrence_count=current.occurrence_count + 1)
            else:
                by_code[finding.code] = finding
                ordered.append(finding.code)
        return tuple(by_code[code] for code in ordered)

    def _merge_session_findings(self, findings: tuple[RiskFinding, ...]) -> tuple[RiskFinding, ...]:
        merged = list(self._session_state.findings)
        for finding in findings:
            for index, existing in enumerate(merged):
                if existing.code is finding.code:
                    merged[index] = replace(existing, occurrence_count=existing.occurrence_count + finding.occurrence_count)
                    break
            else:
                merged.append(finding)
        return tuple(merged[-50:])

    def _session_payload(self) -> dict:
        return {
            "trading_date": self._session_state.trading_date.isoformat(),
            "trades_taken": self._session_state.trades_taken,
            "consecutive_losses": self._session_state.consecutive_losses,
            "manual_lock_active": self._session_state.manual_lock_active,
            "emergency_lock_active": self._session_state.emergency_lock_active,
            "current_open_risk": self._session_state.current_open_risk,
            "instrument_open_risk": dict(sorted(self._session_state.instrument_open_risk.items())),
        }

    def _canonicalize_snapshot(self, snapshot: RiskSnapshot) -> RiskSnapshot:
        if not isinstance(snapshot, RiskSnapshot):
            raise TypeError("RiskEngine expects a RiskSnapshot object.")

        symbol = self._normalize_symbol(snapshot.symbol)
        timeframe = self._normalize_timeframe(snapshot.timeframe)
        if symbol != self._symbol:
            raise ValueError("RiskSnapshot symbol does not match engine context.")
        if timeframe != self._timeframe:
            raise ValueError("RiskSnapshot timeframe does not match engine context.")
        if not isinstance(snapshot.timestamp, datetime):
            raise ValueError("RiskSnapshot timestamp must be a datetime.")

        timestamp_is_aware = snapshot.timestamp.tzinfo is not None
        if self._timestamp_is_aware is not None and timestamp_is_aware != self._timestamp_is_aware:
            raise ValueError("RiskSnapshot timestamp timezone-awareness mode changed.")

        strategy = self._validate_strategy(snapshot.strategy, symbol, timeframe, snapshot.timestamp)
        policy = self._validate_policy(snapshot.policy)
        account = self._validate_account(snapshot.account)
        trade_plan = self._validate_trade_plan(snapshot.trade_plan)
        self._validate_strategy_structure(strategy)

        canonical = RiskSnapshot(symbol, timeframe, snapshot.timestamp, strategy, policy, account, trade_plan)
        if self._timestamp_is_aware is None:
            self._timestamp_is_aware = timestamp_is_aware
        return canonical

    def _validate_strategy(
        self,
        strategy: StrategyDecisionState,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
    ) -> StrategyDecisionState:
        if not isinstance(strategy, StrategyDecisionState):
            raise ValueError("strategy must be a StrategyDecisionState.")
        if self._normalize_symbol(strategy.symbol) != symbol:
            raise ValueError("StrategyDecisionState symbol does not match risk context.")
        if self._normalize_timeframe(strategy.timeframe) != timeframe:
            raise ValueError("StrategyDecisionState timeframe does not match risk context.")
        if strategy.timestamp != timestamp:
            raise ValueError("StrategyDecisionState timestamp must match RiskSnapshot timestamp.")
        return strategy

    def _validate_strategy_structure(self, strategy: StrategyDecisionState) -> None:
        if strategy.decision is StrategyDecision.TRADE_ELIGIBLE:
            if strategy.direction not in {TradeDirection.BULLISH, TradeDirection.BEARISH}:
                raise ValueError("Eligible strategy must have a directional side.")
            if (
                strategy.entry_reference is EntryReference.NONE
                or strategy.stop_reference is StopReference.NONE
                or strategy.target_reference is TargetReference.NONE
                or strategy.block_reason is not BlockReason.NONE
            ):
                raise ValueError("Eligible strategy contains incomplete references or a block reason.")

    def _validate_policy(self, policy: RiskPolicy) -> RiskPolicy:
        if not isinstance(policy, RiskPolicy):
            raise ValueError("policy must be a RiskPolicy.")
        max_risk = self._positive_real("max_risk_percent", policy.max_risk_percent)
        reduced_risk = self._positive_real("reduced_risk_percent", policy.reduced_risk_percent)
        daily_loss = self._positive_real("max_daily_loss_percent", policy.max_daily_loss_percent)
        if max_risk > 100 or daily_loss > 100:
            raise ValueError("Risk percentages must be less than or equal to 100.")
        if reduced_risk > max_risk:
            raise ValueError("reduced_risk_percent must be less than or equal to max_risk_percent.")
        max_losses = self._positive_int("max_consecutive_losses", policy.max_consecutive_losses)
        reduce_losses = self._non_negative_int("reduced_after_consecutive_losses", policy.reduced_after_consecutive_losses)
        max_trades = self._positive_int("max_trades_per_day", policy.max_trades_per_day)
        reduce_trades = self._non_negative_int("reduced_after_trades", policy.reduced_after_trades)
        max_lots = self._positive_int("max_lots", policy.max_lots)
        min_rr = self._positive_real("minimum_reward_risk", policy.minimum_reward_risk)
        if reduce_losses >= max_losses:
            raise ValueError("reduced_after_consecutive_losses must be less than max_consecutive_losses.")
        if reduce_trades >= max_trades:
            raise ValueError("reduced_after_trades must be less than max_trades_per_day.")
        return RiskPolicy(max_risk, reduced_risk, daily_loss, max_losses, reduce_losses, max_trades, reduce_trades, max_lots, min_rr)

    def _validate_account(self, account: AccountRiskState) -> AccountRiskState:
        if not isinstance(account, AccountRiskState):
            raise ValueError("account must be an AccountRiskState.")
        equity = self._positive_real("account_equity", account.account_equity)
        pnl = self._finite_real("realized_pnl_today", account.realized_pnl_today)
        trades = self._non_negative_int("trades_today", account.trades_today)
        losses = self._non_negative_int("consecutive_losses", account.consecutive_losses)
        return AccountRiskState(equity, pnl, trades, losses)

    def _validate_trade_plan(self, trade_plan: TradeRiskPlan) -> TradeRiskPlan:
        if not isinstance(trade_plan, TradeRiskPlan):
            raise ValueError("trade_plan must be a TradeRiskPlan.")
        entry = self._positive_real("entry_price", trade_plan.entry_price)
        stop = self._positive_real("stop_price", trade_plan.stop_price)
        target = self._positive_real("target_price", trade_plan.target_price)
        lot_size = self._positive_int("lot_size", trade_plan.lot_size)
        requested_lots = self._positive_int("requested_lots", trade_plan.requested_lots)
        return TradeRiskPlan(entry, stop, target, lot_size, requested_lots)

    def _normalize_direction(self, direction) -> TradeDirection:
        if isinstance(direction, TradeDirection):
            if direction is TradeDirection.NONE:
                raise ValueError("direction must be bullish or bearish")
            return direction
        if not isinstance(direction, str):
            raise ValueError("direction must be a TradeDirection or text")
        normalized = direction.strip().lower()
        if normalized in {"bullish", "long", "buy"}:
            return TradeDirection.BULLISH
        if normalized in {"bearish", "short", "sell"}:
            return TradeDirection.BEARISH
        raise ValueError("direction must be bullish or bearish")

    def _normalize_optional_direction(self, direction) -> TradeDirection | None:
        if direction is None:
            return None
        return self._normalize_direction(direction)

    def _resolve_number(self, preferred, fallback, name: str) -> float:
        value = fallback if preferred is None else preferred
        return self._finite_real(name, value)

    def _optional_positive_real(self, name: str, value) -> float | None:
        if value is None:
            return None
        return self._positive_real(name, value)

    def _require_aware(self, value, name: str) -> datetime:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware datetime.")
        return value.astimezone(IST)

    def _percentage_like(self, name: str, value: Real) -> float:
        number = self._positive_real(name, value)
        if number > 100:
            raise ValueError(f"{name} must be less than or equal to 100.")
        return number

    def _non_negative_real(self, name: str, value: Real) -> float:
        number = self._finite_real(name, value)
        if number < 0:
            raise ValueError(f"{name} must be greater than or equal to zero.")
        return number

    def _non_negative_int_value(self, name: str, value: int) -> int:
        return self._non_negative_int(name, value)

    def _normalize_symbol(self, symbol: str) -> str:
        if not isinstance(symbol, str):
            raise ValueError("RiskEngine symbol must be a string.")
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("RiskEngine symbol cannot be empty.")
        return normalized

    def _normalize_timeframe(self, timeframe: str) -> str:
        if not isinstance(timeframe, str):
            raise ValueError("RiskEngine timeframe must be a string.")
        normalized = timeframe.strip()
        if not normalized:
            raise ValueError("RiskEngine timeframe cannot be empty.")
        return normalized

    def _finite_real(self, name: str, value: Real) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be a finite real number.")
        number = float(value)
        if not isfinite(number):
            raise ValueError(f"{name} must be a finite real number.")
        return number

    def _positive_real(self, name: str, value: Real) -> float:
        number = self._finite_real(name, value)
        if number <= 0:
            raise ValueError(f"{name} must be greater than zero.")
        return number

    def _non_negative_int(self, name: str, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer.")
        if value < 0:
            raise ValueError(f"{name} must be greater than or equal to zero.")
        return value

    def _positive_int(self, name: str, value: int) -> int:
        integer = self._non_negative_int(name, value)
        if integer <= 0:
            raise ValueError(f"{name} must be greater than zero.")
        return integer


def _stable_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
