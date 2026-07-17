"""
Risk Engine V1.
"""

from datetime import datetime
from math import isfinite
from numbers import Real

from core.base_engine import BaseEngine
from core.events import RISK_UPDATED
from engines.risk.calculator import RiskCalculator
from engines.risk.models import (
    AccountRiskState,
    RiskDecisionState,
    RiskPolicy,
    RiskSnapshot,
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

    def clear(self) -> None:
        self.reset()

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
