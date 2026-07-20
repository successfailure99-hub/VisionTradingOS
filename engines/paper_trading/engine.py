"""
Deterministic Paper Trading & Position Lifecycle Engine V1.
"""

from dataclasses import replace
from datetime import time
from math import isfinite
from zoneinfo import ZoneInfo

from application.enums import ExecutionSafetyMode
from core.models.candle import Candle
from core.models.tick import Tick
from engines.paper_trading.configuration import PaperTradingConfiguration
from engines.paper_trading.enums import PaperEntryMode, PaperExitType, PaperOrderState, PaperPositionState
from engines.paper_trading.events import (
    PAPER_ORDER_CANCELLED,
    PAPER_ORDER_CREATED,
    PAPER_ORDER_EXPIRED,
    PAPER_ORDER_TRIGGERED,
    PAPER_POSITION_CLOSED,
    PAPER_POSITION_OPENED,
    PAPER_POSITION_UPDATED,
    PAPER_TRADE_RECORDED,
)
from engines.paper_trading.models import (
    PaperJournalSummary,
    PaperOrder,
    PaperPosition,
    PaperTradeRecord,
    PaperTradingDiagnostics,
    PaperTradingSnapshot,
)
from engines.order_management.models import OrderState
from engines.risk.enums import RiskDecision
from engines.risk.models import RiskDecisionState, TradePlan
from engines.strategy.enums import StrategyDecision, TradeDirection


IST = ZoneInfo("Asia/Kolkata")
SESSION_CLOSE = time(15, 30)
SAFE_MODES = {ExecutionSafetyMode.ANALYSIS_ONLY, ExecutionSafetyMode.DRY_RUN}


class PaperTradingEngine:
    def __init__(
        self,
        event_bus,
        *,
        instrument: str,
        timeframe: str,
        safety_mode: ExecutionSafetyMode,
        configuration: PaperTradingConfiguration | None = None,
    ):
        self._event_bus = event_bus
        self._instrument = _text(instrument, "instrument").upper()
        self._timeframe = _text(timeframe, "timeframe")
        self._safety_mode = safety_mode
        self._configuration = configuration or PaperTradingConfiguration()
        if not isinstance(self._configuration, PaperTradingConfiguration):
            raise TypeError("configuration must be PaperTradingConfiguration")
        self._order: PaperOrder | None = None
        self._position: PaperPosition | None = None
        self._records: dict[str, PaperTradeRecord] = {}
        self._processed_plan_ids: set[str] = set()
        self._closed_position_ids: set[str] = set()
        self._trade_contexts: dict[str, dict[str, object]] = {}
        self._previous_price: float | None = None
        self._latest_price: float | None = None
        self._last_event = "-"
        self._last_error: str | None = None
        self._plans_received = 0
        self._orders_created = 0
        self._orders_triggered = 0
        self._orders_cancelled = 0
        self._orders_expired = 0
        self._positions_opened = 0
        self._positions_closed = 0

    @property
    def active_order(self) -> PaperOrder | None:
        return self._order if self._order is not None and self._order.state is PaperOrderState.PENDING else None

    @property
    def active_position(self) -> PaperPosition | None:
        return self._position if self._position is not None and self._position.state is PaperPositionState.OPEN else None

    def receive_plan(self, plan: TradePlan | None, risk: RiskDecisionState | None, strategy=None, ai_reasoning=None) -> PaperTradingSnapshot:
        if not self._enabled_safe():
            self._last_error = "Paper trading disabled by unsafe runtime mode"
            return self.snapshot()
        if plan is None or risk is None or risk.decision is not RiskDecision.APPROVED or not risk.trade_plan_ready:
            return self.snapshot()
        if plan.instrument != self._instrument or risk.symbol != self._instrument:
            return self.snapshot()
        self._plans_received += 1
        if not self._configuration.auto_create_order:
            return self.snapshot()
        if self.active_order is not None or self.active_position is not None:
            return self.snapshot()
        if plan.plan_id in self._processed_plan_ids:
            return self.snapshot()
        order = PaperOrder(
            paper_order_id=f"paper-order:{plan.plan_id}",
            plan_id=plan.plan_id,
            instrument=plan.instrument,
            created_at=plan.created_at,
            updated_at=plan.created_at,
            direction=plan.strategy_direction,
            entry_type=plan.entry_type,
            entry_price=plan.entry_price,
            stop_price=plan.stop_price,
            target_price=plan.target_price,
            quantity=plan.approved_quantity,
            lot_size=plan.lot_size,
            approved_lots=plan.approved_lots,
            state=PaperOrderState.PENDING,
            valid_until=plan.valid_until,
            source_plan_identity=plan.source_strategy_id,
        )
        self._order = order
        self._trade_contexts[plan.plan_id] = _trade_context(
            plan,
            strategy=strategy,
            ai_reasoning=ai_reasoning,
            timeframe=self._timeframe,
        )
        self._processed_plan_ids.add(plan.plan_id)
        self._orders_created += 1
        self._last_event = PAPER_ORDER_CREATED
        self._safe_publish(PAPER_ORDER_CREATED, order)
        return self.snapshot()

    def submit_managed_order(self, order: OrderState, *, execution_plan, purpose: str) -> str:
        if not self._enabled_safe():
            self._last_error = "Paper trading disabled by unsafe runtime mode"
            raise RuntimeError(self._last_error)
        if not isinstance(order, OrderState):
            raise TypeError("order must be OrderState")
        if order.symbol != self._instrument:
            raise ValueError("Managed order instrument does not match paper runtime.")
        self._orders_created += 1
        self._last_event = PAPER_ORDER_CREATED
        return f"paper-submission:{purpose}:{order.client_order_id}"

    def cancel_managed_order(self, order_id: str, *, timestamp, reason: str) -> str:
        if not self._enabled_safe():
            self._last_error = "Paper trading disabled by unsafe runtime mode"
            raise RuntimeError(self._last_error)
        _text(order_id, "order_id")
        _text(reason, "reason")
        self._orders_cancelled += 1
        self._last_event = PAPER_ORDER_CANCELLED
        return f"paper-cancel:{order_id}"

    def on_tick(self, tick: Tick, *, strategy=None, risk: RiskDecisionState | None = None) -> PaperTradeRecord | None:
        if not self._enabled_safe():
            return None
        if tick.symbol.value != self._instrument:
            return None
        price = _positive_price(tick.last_price)
        if price is None:
            return None
        previous = self._latest_price
        self._previous_price = previous
        self._latest_price = price
        now = tick.timestamp
        self._expire_or_cancel_pending(now, price, strategy=strategy, risk=risk)
        if self.active_order is not None and _entry_triggered(self.active_order, previous, price):
            self._trigger_order(now, price)
        if self.active_position is not None:
            self._mark_position(now, price)
            return self._check_position_exit(now, price, strategy=strategy)
        return None

    def on_candle(self, candle: Candle, *, strategy=None, risk: RiskDecisionState | None = None) -> PaperTradeRecord | None:
        if not self._enabled_safe() or candle.symbol != self._instrument:
            return None
        self._expire_or_cancel_pending(candle.end_time, candle.close, strategy=strategy, risk=risk)
        if self.active_order is not None and _range_contains(candle.low, candle.high, self.active_order.entry_price):
            self._trigger_order(candle.end_time, _entry_fill(self.active_order, candle.close, self._configuration.slippage_points))
        if self.active_position is not None:
            position = self.active_position
            stop_hit = _range_contains(candle.low, candle.high, position.stop_price)
            target_hit = _range_contains(candle.low, candle.high, position.target_price)
            if stop_hit and target_hit:
                return self._close_position(candle.end_time, _stop_exit_price(position, position.stop_price), PaperExitType.STOP_LOSS)
            if stop_hit:
                return self._close_position(candle.end_time, _stop_exit_price(position, candle.close), PaperExitType.STOP_LOSS)
            if target_hit:
                return self._close_position(candle.end_time, position.target_price, PaperExitType.TARGET)
        return None

    def shutdown(self, timestamp=None) -> PaperTradeRecord | None:
        now = timestamp or _now()
        if self.active_order is not None:
            self._cancel_order(now, "SYSTEM_SHUTDOWN")
        if self.active_position is not None and self._configuration.close_at_session_end:
            price = self._latest_price or self.active_position.last_price
            return self._close_position(now, price, PaperExitType.SYSTEM_SHUTDOWN)
        return None

    def reset(self) -> None:
        self._order = None
        self._position = None
        self._records.clear()
        self._processed_plan_ids.clear()
        self._closed_position_ids.clear()
        self._trade_contexts.clear()
        self._previous_price = None
        self._latest_price = None
        self._last_event = "-"
        self._last_error = None
        self._plans_received = 0
        self._orders_created = 0
        self._orders_triggered = 0
        self._orders_cancelled = 0
        self._orders_expired = 0
        self._positions_opened = 0
        self._positions_closed = 0

    def snapshot(self) -> PaperTradingSnapshot:
        summary = _summary(tuple(self._records.values()))
        diagnostics = PaperTradingDiagnostics(
            paper_trading_enabled=self._configuration.enabled,
            safe_mode_confirmed=self._enabled_safe(),
            plans_received=self._plans_received,
            orders_created=self._orders_created,
            orders_triggered=self._orders_triggered,
            orders_cancelled=self._orders_cancelled,
            orders_expired=self._orders_expired,
            positions_opened=self._positions_opened,
            positions_closed=self._positions_closed,
            journal_records=summary.record_count,
            last_event=self._last_event,
            last_error=self._last_error,
            broker_order_calls=0,
        )
        return PaperTradingSnapshot(
            enabled=self._configuration.enabled,
            safe_mode_confirmed=self._enabled_safe(),
            order=self._order,
            position=self.active_position,
            journal_summary=summary,
            latest_record=summary.latest_record,
            last_event=self._last_event,
            last_error=self._last_error,
            diagnostics=diagnostics,
        )

    def _trigger_order(self, timestamp, market_price: float) -> None:
        order = self.active_order
        if order is None:
            return
        fill_price = _entry_fill(order, market_price, self._configuration.slippage_points)
        triggered = replace(order, state=PaperOrderState.TRIGGERED, updated_at=timestamp, triggered_at=timestamp, trigger_price=fill_price)
        self._order = triggered
        self._orders_triggered += 1
        self._last_event = PAPER_ORDER_TRIGGERED
        self._safe_publish(PAPER_ORDER_TRIGGERED, triggered)
        position = PaperPosition(
            position_id=f"paper-position:{order.plan_id}",
            paper_order_id=order.paper_order_id,
            plan_id=order.plan_id,
            instrument=order.instrument,
            direction=order.direction,
            quantity=order.quantity,
            lot_size=order.lot_size,
            opened_at=timestamp,
            entry_price=fill_price,
            last_price=fill_price,
            stop_price=order.stop_price,
            target_price=order.target_price,
            unrealized_pnl=0.0,
            maximum_favourable_excursion=0.0,
            maximum_adverse_excursion=0.0,
            state=PaperPositionState.OPEN,
        )
        self._position = position
        self._positions_opened += 1
        self._last_event = PAPER_POSITION_OPENED
        self._safe_publish(PAPER_POSITION_OPENED, position)

    def _mark_position(self, timestamp, price: float) -> None:
        position = self.active_position
        if position is None:
            return
        unrealized = _pnl(position.direction, position.entry_price, price, position.quantity)
        mfe, mae = _excursions(position.direction, position.entry_price, price, position.quantity)
        marked = replace(
            position,
            last_price=price,
            unrealized_pnl=unrealized,
            maximum_favourable_excursion=max(position.maximum_favourable_excursion, mfe),
            maximum_adverse_excursion=max(position.maximum_adverse_excursion, mae),
        )
        self._position = marked
        self._last_event = PAPER_POSITION_UPDATED
        self._safe_publish(PAPER_POSITION_UPDATED, marked)

    def _check_position_exit(self, timestamp, price: float, *, strategy=None) -> PaperTradeRecord | None:
        position = self.active_position
        if position is None:
            return None
        if position.direction is TradeDirection.BULLISH:
            if price <= position.stop_price:
                return self._close_position(timestamp, _stop_exit_price(position, price), PaperExitType.STOP_LOSS)
            if price >= position.target_price:
                return self._close_position(timestamp, position.target_price, PaperExitType.TARGET)
        if position.direction is TradeDirection.BEARISH:
            if price >= position.stop_price:
                return self._close_position(timestamp, _stop_exit_price(position, price), PaperExitType.STOP_LOSS)
            if price <= position.target_price:
                return self._close_position(timestamp, position.target_price, PaperExitType.TARGET)
        if self._configuration.exit_on_strategy_invalidation and strategy is not None and strategy.decision is StrategyDecision.NO_TRADE:
            return self._close_position(timestamp, price, PaperExitType.STRATEGY_INVALIDATED)
        if self._configuration.close_at_session_end and timestamp.astimezone(IST).time() >= SESSION_CLOSE:
            return self._close_position(timestamp, price, PaperExitType.SESSION_CLOSE)
        return None

    def _close_position(self, timestamp, exit_price: float, exit_type: PaperExitType) -> PaperTradeRecord | None:
        position = self.active_position
        if position is None or position.position_id in self._closed_position_ids:
            return None
        gross = _pnl(position.direction, position.entry_price, exit_price, position.quantity)
        fees = round(self._configuration.fixed_fee_per_trade + (abs(gross) * self._configuration.fee_percentage / 100), 2)
        net = round(gross - fees, 2)
        holding = int((timestamp - position.opened_at).total_seconds())
        closed = replace(
            position,
            last_price=exit_price,
            unrealized_pnl=0.0,
            state=PaperPositionState.CLOSED,
            closed_at=timestamp,
            exit_price=exit_price,
            exit_type=exit_type,
            realized_pnl=net,
            holding_seconds=holding,
        )
        self._position = closed
        self._closed_position_ids.add(position.position_id)
        self._positions_closed += 1
        context = self._trade_contexts.get(position.plan_id, {})
        trade = PaperTradeRecord(
            trade_id=f"paper-trade:{position.plan_id}",
            position_id=position.position_id,
            paper_order_id=position.paper_order_id,
            plan_id=position.plan_id,
            instrument=position.instrument,
            direction=position.direction,
            quantity=position.quantity,
            lot_size=position.lot_size,
            entry_time=position.opened_at,
            entry_price=position.entry_price,
            exit_time=timestamp,
            exit_price=exit_price,
            stop_price=position.stop_price,
            target_price=position.target_price,
            exit_type=exit_type,
            gross_pnl=gross,
            fees=fees,
            net_pnl=net,
            reward_risk_planned=_planned_rr(position),
            reward_risk_realized=_realized_rr(position, exit_price),
            maximum_favourable_excursion=position.maximum_favourable_excursion,
            maximum_adverse_excursion=position.maximum_adverse_excursion,
            holding_seconds=holding,
            strategy_setup=str(context.get("strategy_setup", "-")),
            strategy_confidence=str(context.get("strategy_confidence", "-")),
            strategy_reasoning=tuple(context.get("strategy_reasoning", ())),
            trading_date=timestamp.astimezone(IST).date(),
            entry_type=str(context.get("entry_type", "-")),
            timeframe=str(context.get("timeframe", self._timeframe)),
            ai_confidence=context.get("ai_confidence"),
            ai_decision=str(context.get("ai_decision", "-")),
            ai_reasoning_summary=str(context.get("ai_reasoning_summary", "-")),
            price_action_setup=str(context.get("price_action_setup", "-")),
            market_phase=str(context.get("market_phase", "-")),
            day_bias=str(context.get("day_bias", "-")),
            option_chain_bias=str(context.get("option_chain_bias", "-")),
            cpr_relationship=str(context.get("cpr_relationship", "-")),
            cpr_width_classification=str(context.get("cpr_width_classification", "-")),
            camarilla_relationship=str(context.get("camarilla_relationship", "-")),
            vwap_relationship=str(context.get("vwap_relationship", "-")),
            source_strategy_id=str(context.get("source_strategy_id", "-")),
            source_plan_identity=str(context.get("source_plan_identity", "-")),
        )
        self._records.setdefault(trade.trade_id, trade)
        self._last_event = PAPER_POSITION_CLOSED
        self._safe_publish(PAPER_POSITION_CLOSED, closed)
        self._last_event = PAPER_TRADE_RECORDED
        self._safe_publish(PAPER_TRADE_RECORDED, trade)
        return trade

    def _expire_or_cancel_pending(self, timestamp, price: float, *, strategy=None, risk: RiskDecisionState | None = None) -> None:
        order = self.active_order
        if order is None:
            return
        if timestamp >= order.valid_until:
            expired = replace(order, state=PaperOrderState.EXPIRED, updated_at=timestamp, expired_at=timestamp)
            self._order = expired
            self._orders_expired += 1
            self._last_event = PAPER_ORDER_EXPIRED
            self._safe_publish(PAPER_ORDER_EXPIRED, expired)
            return
        if self._configuration.cancel_pending_at_session_end and timestamp.astimezone(IST).time() >= SESSION_CLOSE:
            self._cancel_order(timestamp, "SESSION_CLOSE")
            return
        if risk is not None and getattr(risk, "plan_id", None) == order.plan_id and risk.decision is not RiskDecision.APPROVED:
            self._cancel_order(timestamp, "RISK_WITHDRAWN")
            return
        if strategy is not None:
            if strategy.decision is StrategyDecision.NO_TRADE:
                self._cancel_order(timestamp, "STRATEGY_NO_TRADE")
                return
            if getattr(strategy, "direction", order.direction) is not order.direction:
                self._cancel_order(timestamp, "DIRECTION_REVERSED")
                return
        if order.direction is TradeDirection.BULLISH and (price <= order.stop_price or price >= order.target_price):
            self._cancel_order(timestamp, "PRE_ENTRY_LEVEL_TOUCHED")
        if order.direction is TradeDirection.BEARISH and (price >= order.stop_price or price <= order.target_price):
            self._cancel_order(timestamp, "PRE_ENTRY_LEVEL_TOUCHED")

    def _cancel_order(self, timestamp, reason: str) -> None:
        order = self.active_order
        if order is None:
            return
        cancelled = replace(order, state=PaperOrderState.CANCELLED, updated_at=timestamp, cancelled_at=timestamp, rejection_reason=reason)
        self._order = cancelled
        self._orders_cancelled += 1
        self._last_event = PAPER_ORDER_CANCELLED
        self._safe_publish(PAPER_ORDER_CANCELLED, cancelled)

    def _enabled_safe(self) -> bool:
        return self._configuration.enabled and self._safety_mode in SAFE_MODES

    def _safe_publish(self, event_name: str, payload) -> None:
        try:
            self._event_bus.publish(event_name, payload)
        except Exception as exc:
            self._last_error = exc.__class__.__name__


def _entry_triggered(order: PaperOrder, previous: float | None, current: float) -> bool:
    if previous is None:
        return False
    mode = _entry_mode(order.entry_type)
    if order.direction is TradeDirection.BULLISH:
        if mode is PaperEntryMode.BREAKOUT:
            return previous < order.entry_price <= current
        return previous > order.entry_price >= current
    if mode is PaperEntryMode.BREAKOUT:
        return previous > order.entry_price >= current
    return previous < order.entry_price <= current


def _entry_mode(entry_type: str) -> PaperEntryMode:
    normalized = str(entry_type).lower()
    if "breakout" in normalized or "breakdown" in normalized or "stop" in normalized:
        return PaperEntryMode.BREAKOUT
    return PaperEntryMode.RETEST


def _entry_fill(order: PaperOrder, market_price: float, slippage: float) -> float:
    if order.direction is TradeDirection.BULLISH:
        return round(max(order.entry_price, market_price) + slippage, 4)
    return round(min(order.entry_price, market_price) - slippage, 4)


def _stop_exit_price(position: PaperPosition, market_price: float) -> float:
    if position.direction is TradeDirection.BULLISH:
        return round(min(position.stop_price, market_price), 4)
    return round(max(position.stop_price, market_price), 4)


def _pnl(direction: TradeDirection, entry: float, exit_: float, quantity: int) -> float:
    if direction is TradeDirection.BULLISH:
        return round((exit_ - entry) * quantity, 2)
    return round((entry - exit_) * quantity, 2)


def _excursions(direction: TradeDirection, entry: float, price: float, quantity: int) -> tuple[float, float]:
    if direction is TradeDirection.BULLISH:
        return round(max(0.0, price - entry) * quantity, 2), round(max(0.0, entry - price) * quantity, 2)
    return round(max(0.0, entry - price) * quantity, 2), round(max(0.0, price - entry) * quantity, 2)


def _planned_rr(position: PaperPosition) -> float:
    if position.direction is TradeDirection.BULLISH:
        return round((position.target_price - position.entry_price) / (position.entry_price - position.stop_price), 4)
    return round((position.entry_price - position.target_price) / (position.stop_price - position.entry_price), 4)


def _realized_rr(position: PaperPosition, exit_price: float) -> float | None:
    risk = abs(position.entry_price - position.stop_price)
    if risk <= 0:
        return None
    reward = exit_price - position.entry_price if position.direction is TradeDirection.BULLISH else position.entry_price - exit_price
    return round(reward / risk, 4)


def _summary(records: tuple[PaperTradeRecord, ...]) -> PaperJournalSummary:
    ordered = tuple(records)
    if not ordered:
        return PaperJournalSummary()
    wins = tuple(item for item in ordered if item.net_pnl > 0)
    losses = tuple(item for item in ordered if item.net_pnl < 0)
    gross_profit = sum(item.net_pnl for item in wins)
    gross_loss = abs(sum(item.net_pnl for item in losses))
    return PaperJournalSummary(
        record_count=len(ordered),
        latest_record=ordered[-1],
        daily_realized_pnl=round(sum(item.net_pnl for item in ordered), 2),
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=round(len(wins) / len(ordered) * 100, 2),
        average_win=round(gross_profit / len(wins), 2) if wins else None,
        average_loss=round(-gross_loss / len(losses), 2) if losses else None,
        profit_factor=round(gross_profit / gross_loss, 4) if gross_loss else None,
    )


def _trade_context(plan, *, strategy=None, ai_reasoning=None, timeframe: str) -> dict[str, object]:
    market_context = getattr(strategy, "market_context", None)
    return {
        "entry_type": getattr(plan, "entry_type", "-"),
        "timeframe": timeframe,
        "strategy_setup": _label(getattr(plan, "strategy_setup", None)),
        "strategy_confidence": _label(getattr(strategy, "confidence", None)),
        "strategy_reasoning": tuple(getattr(plan, "reasoning", ()) or ()),
        "ai_confidence": _optional_float(getattr(ai_reasoning, "confidence", None)),
        "ai_decision": _label(getattr(ai_reasoning, "decision", None)),
        "ai_reasoning_summary": _label(getattr(ai_reasoning, "explanation", None) or getattr(ai_reasoning, "market_summary", None)),
        "price_action_setup": _label(getattr(strategy, "setup_quality", None)),
        "market_phase": _label(getattr(market_context, "market_phase", None)),
        "day_bias": _label(getattr(market_context, "market_bias", None)),
        "option_chain_bias": _label(getattr(market_context, "option_chain_direction", None)),
        "cpr_relationship": _label(getattr(market_context, "cpr_relationship", None)),
        "cpr_width_classification": _label(getattr(market_context, "cpr_width_classification", None)),
        "camarilla_relationship": _label(getattr(market_context, "camarilla_relationship", None)),
        "vwap_relationship": _label(getattr(market_context, "vwap_relationship", None)),
        "source_strategy_id": _label(getattr(plan, "source_strategy_id", None)),
        "source_plan_identity": _label(getattr(plan, "source_strategy_id", None)),
    }


def _label(value) -> str:
    raw = getattr(value, "value", value)
    text = str(raw).strip() if raw is not None else ""
    return text or "-"


def _optional_float(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _positive_price(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) and number > 0 else None


def _range_contains(low: float, high: float, price: float) -> bool:
    return low <= price <= high


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _now():
    from datetime import datetime

    return datetime.now(IST)
