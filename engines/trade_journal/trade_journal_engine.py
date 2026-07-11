"""
Trade Journal Engine V1.
"""

from datetime import datetime
from math import isfinite
from numbers import Real

from core.base_engine import BaseEngine
from core.events import TRADE_RECORDED
from engines.ai_reasoning.enums import AIMarketSummary
from engines.ai_reasoning.models import AIReasoningState
from engines.risk.enums import RiskDecision, RiskRejectionReason
from engines.risk.models import RiskDecisionState
from engines.strategy.enums import BlockReason, StrategyDecision, TradeDirection
from engines.strategy.models import StrategyDecisionState
from engines.trade_journal.calculator import TradeJournalCalculator
from engines.trade_journal.enums import JournalFilter, TradeCompliance, TradeExitType, TradeOutcome
from engines.trade_journal.models import TradeJournalRecord, TradeJournalSnapshot, TradeJournalSummary


class TradeJournalEngine(BaseEngine):
    """
    In-memory immutable journal for completed position lifecycles.

    Trade Journal Engine V1 records objective audit entries across multiple
    symbols and timeframes. It does not place orders, modify positions,
    persist data, write files, calculate brokerage, taxes, slippage, charges,
    or net P&L, generate AI commentary, or perform advanced analytics.
    realized_gross_pnl excludes fees and charges. R-multiple uses planned
    risk. Calls are expected to be serialized and single-threaded; persistence
    and advanced analytics are later milestones.
    """

    def __init__(self, event_bus):
        super().__init__(event_bus)
        self._records: dict[str, TradeJournalRecord] = {}
        self._snapshots: dict[str, TradeJournalSnapshot] = {}
        self._summary: TradeJournalSummary = TradeJournalCalculator.empty_summary()
        self._latest_trade_id: str | None = None
        self._last_closed_at: datetime | None = None
        self._timestamp_is_aware: bool | None = None

    @property
    def latest_record(self) -> TradeJournalRecord | None:
        if self._latest_trade_id is None:
            return None
        return self._records[self._latest_trade_id]

    @property
    def summary(self) -> TradeJournalSummary:
        return self._summary

    @property
    def record_count(self) -> int:
        return len(self._records)

    def record(self, snapshot: TradeJournalSnapshot) -> TradeJournalRecord:
        canonical = self._canonicalize_snapshot(snapshot)
        existing = self._records.get(canonical.trade_id)
        if existing is not None:
            if canonical == self._snapshots[canonical.trade_id]:
                return existing
            raise ValueError("Duplicate trade_id cannot overwrite an existing journal record.")

        self._validate_timestamp(canonical.closed_at)
        record = TradeJournalCalculator.create_record(canonical)
        self._snapshots[canonical.trade_id] = canonical
        self._records[canonical.trade_id] = record
        self._summary = TradeJournalCalculator.calculate_summary(tuple(self._records.values()))
        self._latest_trade_id = canonical.trade_id
        self._accept_timestamp(canonical.closed_at)
        self._data = record
        self._event_bus.publish(TRADE_RECORDED, record)
        return record

    def process(self, snapshot: TradeJournalSnapshot) -> TradeJournalRecord:
        return self.record(snapshot)

    def get_record(self, trade_id: str) -> TradeJournalRecord | None:
        if not isinstance(trade_id, str):
            return None
        return self._records.get(trade_id.strip())

    def get_records(self) -> tuple[TradeJournalRecord, ...]:
        return tuple(self._records.values())

    def filter_records(self, filter_type: JournalFilter) -> tuple[TradeJournalRecord, ...]:
        if not isinstance(filter_type, JournalFilter):
            raise TypeError("filter_type must be a JournalFilter.")
        records = self.get_records()
        if filter_type is JournalFilter.ALL:
            return records
        if filter_type is JournalFilter.WINNERS:
            return tuple(record for record in records if record.outcome is TradeOutcome.WIN)
        if filter_type is JournalFilter.LOSERS:
            return tuple(record for record in records if record.outcome is TradeOutcome.LOSS)
        if filter_type is JournalFilter.BREAKEVEN:
            return tuple(record for record in records if record.outcome is TradeOutcome.BREAKEVEN)
        if filter_type is JournalFilter.COMPLIANT:
            return tuple(record for record in records if record.compliance is TradeCompliance.COMPLIANT)
        return tuple(record for record in records if record.compliance is TradeCompliance.NON_COMPLIANT)

    def reset(self) -> None:
        super().clear()
        self._records.clear()
        self._snapshots.clear()
        self._summary = TradeJournalCalculator.empty_summary()
        self._latest_trade_id = None
        self._last_closed_at = None
        self._timestamp_is_aware = None

    def clear(self) -> None:
        self.reset()

    def _canonicalize_snapshot(self, snapshot: TradeJournalSnapshot) -> TradeJournalSnapshot:
        if not isinstance(snapshot, TradeJournalSnapshot):
            raise TypeError("TradeJournalEngine expects a TradeJournalSnapshot object.")

        trade_id = self._normalize_text(snapshot.trade_id, "trade_id")
        symbol = self._normalize_text(snapshot.symbol, "symbol").upper()
        exchange = self._normalize_text(snapshot.exchange, "exchange").upper()
        timeframe = self._normalize_text(snapshot.timeframe, "timeframe")
        self._validate_datetimes(snapshot.opened_at, snapshot.closed_at)
        self._validate_direction(snapshot.direction)
        entry_quantity = self._positive_int("entry_quantity", snapshot.entry_quantity)
        exit_quantity = self._positive_int("exit_quantity", snapshot.exit_quantity)
        if entry_quantity != exit_quantity:
            raise ValueError("TradeJournalSnapshot requires fully closed equal entry and exit quantities.")

        average_entry_price = self._positive_real("average_entry_price", snapshot.average_entry_price)
        average_exit_price = self._positive_real("average_exit_price", snapshot.average_exit_price)
        planned_stop_price = self._positive_real("planned_stop_price", snapshot.planned_stop_price)
        planned_target_price = self._positive_real("planned_target_price", snapshot.planned_target_price)
        planned_risk_amount = self._positive_real("planned_risk_amount", snapshot.planned_risk_amount)
        planned_reward_amount = self._non_negative_real("planned_reward_amount", snapshot.planned_reward_amount)
        realized_gross_pnl = self._finite_real("realized_gross_pnl", snapshot.realized_gross_pnl)
        entry_order_ids = self._normalize_order_ids(snapshot.entry_order_ids, "entry_order_ids")
        exit_order_ids = self._normalize_order_ids(snapshot.exit_order_ids, "exit_order_ids")
        if set(entry_order_ids) & set(exit_order_ids):
            raise ValueError("Entry and exit order IDs must not overlap.")
        if not isinstance(snapshot.exit_type, TradeExitType):
            raise ValueError("exit_type must be a TradeExitType.")

        self._validate_upstream(
            symbol,
            timeframe,
            snapshot.direction,
            entry_quantity,
            average_entry_price,
            planned_stop_price,
            planned_target_price,
            snapshot.strategy,
            snapshot.risk,
            snapshot.ai_reasoning,
        )

        return TradeJournalSnapshot(
            trade_id=trade_id,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            opened_at=snapshot.opened_at,
            closed_at=snapshot.closed_at,
            direction=snapshot.direction,
            entry_quantity=entry_quantity,
            exit_quantity=exit_quantity,
            average_entry_price=average_entry_price,
            average_exit_price=average_exit_price,
            planned_stop_price=planned_stop_price,
            planned_target_price=planned_target_price,
            planned_risk_amount=planned_risk_amount,
            planned_reward_amount=planned_reward_amount,
            realized_gross_pnl=realized_gross_pnl,
            strategy=snapshot.strategy,
            risk=snapshot.risk,
            ai_reasoning=snapshot.ai_reasoning,
            entry_order_ids=entry_order_ids,
            exit_order_ids=exit_order_ids,
            exit_type=snapshot.exit_type,
        )

    def _validate_upstream(
        self,
        symbol: str,
        timeframe: str,
        direction: TradeDirection,
        entry_quantity: int,
        average_entry_price: float,
        planned_stop_price: float,
        planned_target_price: float,
        strategy: StrategyDecisionState,
        risk: RiskDecisionState,
        ai_reasoning: AIReasoningState,
    ) -> None:
        if not isinstance(strategy, StrategyDecisionState):
            raise TypeError("strategy must be a StrategyDecisionState.")
        if not isinstance(risk, RiskDecisionState):
            raise TypeError("risk must be a RiskDecisionState.")
        if not isinstance(ai_reasoning, AIReasoningState):
            raise TypeError("ai_reasoning must be an AIReasoningState.")
        for name, state in (("strategy", strategy), ("risk", risk), ("ai_reasoning", ai_reasoning)):
            if self._normalize_text(state.symbol, f"{name}.symbol").upper() != symbol:
                raise ValueError(f"{name} symbol does not match journal snapshot.")
            if self._normalize_text(state.timeframe, f"{name}.timeframe") != timeframe:
                raise ValueError(f"{name} timeframe does not match journal snapshot.")
        if strategy.direction is not direction or risk.direction is not direction:
            raise ValueError("Strategy and Risk direction must match journal snapshot.")
        if strategy.decision is not StrategyDecision.TRADE_ELIGIBLE or strategy.block_reason is not BlockReason.NONE:
            raise ValueError("Strategy state is not eligible for journaling.")
        if risk.decision is not RiskDecision.APPROVED or risk.rejection_reason is not RiskRejectionReason.NONE:
            raise ValueError("Risk state is not approved for journaling.")
        if risk.approved_quantity != entry_quantity:
            raise ValueError("Risk approved quantity must match entry quantity.")
        if risk.entry_price != average_entry_price or risk.stop_price != planned_stop_price or risk.target_price != planned_target_price:
            raise ValueError("Risk approved prices must match journal snapshot prices.")
        if strategy.market_bias.value != ai_reasoning.market_summary.value:
            raise ValueError("Strategy market bias must match AI market summary direction.")
        if strategy.confidence is not ai_reasoning.confidence:
            raise ValueError("Strategy confidence must match AI confidence.")
        if strategy.trading_suitability is not ai_reasoning.trading_suitability:
            raise ValueError("Strategy suitability must match AI suitability.")
        if ai_reasoning.market_summary not in {AIMarketSummary.BULLISH, AIMarketSummary.BEARISH}:
            raise ValueError("AI market summary must be directional for a recorded trade.")

    def _validate_datetimes(self, opened_at: datetime, closed_at: datetime) -> None:
        if not isinstance(opened_at, datetime):
            raise ValueError("opened_at must be a datetime.")
        if not isinstance(closed_at, datetime):
            raise ValueError("closed_at must be a datetime.")
        if (opened_at.tzinfo is None) != (closed_at.tzinfo is None):
            raise ValueError("opened_at and closed_at timezone-awareness modes must match.")
        if closed_at < opened_at:
            raise ValueError("closed_at must be greater than or equal to opened_at.")

    def _validate_timestamp(self, closed_at: datetime) -> None:
        timestamp_is_aware = closed_at.tzinfo is not None
        if self._timestamp_is_aware is not None and timestamp_is_aware != self._timestamp_is_aware:
            raise ValueError("Trade journal timestamp timezone-awareness mode changed.")
        if self._last_closed_at is not None and closed_at < self._last_closed_at:
            raise ValueError("Stale TradeJournalSnapshot received.")

    def _accept_timestamp(self, closed_at: datetime) -> None:
        if self._timestamp_is_aware is None:
            self._timestamp_is_aware = closed_at.tzinfo is not None
        self._last_closed_at = closed_at

    def _validate_direction(self, direction: TradeDirection) -> None:
        if direction not in {TradeDirection.BULLISH, TradeDirection.BEARISH}:
            raise ValueError("direction must be BULLISH or BEARISH.")

    def _normalize_order_ids(self, value: tuple[str, ...], name: str) -> tuple[str, ...]:
        if not isinstance(value, tuple) or not value:
            raise ValueError(f"{name} must be a non-empty tuple of order IDs.")
        normalized = tuple(self._normalize_text(order_id, name) for order_id in value)
        if len(set(normalized)) != len(normalized):
            raise ValueError(f"{name} must not contain duplicate IDs.")
        return normalized

    def _normalize_text(self, value: str, name: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string.")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{name} cannot be empty.")
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

    def _non_negative_real(self, name: str, value: Real) -> float:
        number = self._finite_real(name, value)
        if number < 0:
            raise ValueError(f"{name} must be greater than or equal to zero.")
        return number

    def _positive_int(self, name: str, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be a positive integer.")
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero.")
        return value
