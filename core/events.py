"""
====================================================
Vision Trading OS
System Events
====================================================

This module defines all event names used by the
Vision Trading OS Event Bus.

Rules:
- Events are constants.
- Event names are unique.
- Events are grouped by feature.
"""

# ==================================================
# Market Data Events
# ==================================================

NEW_TICK = "new_tick"
MARKET_UPDATED = "market_updated"
MARKET_OPENED = "market_opened"
MARKET_CLOSED = "market_closed"

# ==================================================
# Candle Events
# ==================================================

CANDLE_OPENED = "candle_opened"
CANDLE_UPDATED = "candle_updated"
CANDLE_CLOSED = "candle_closed"

# ==================================================
# Indicator Events
# ==================================================

CAMARILLA_UPDATED = "camarilla_updated"
CPR_UPDATED = "cpr_updated"
VWAP_UPDATED = "vwap_updated"
ADR_UPDATED = "adr_updated"
ADR_PARTIAL = "adr_partial"
ADR_INVALID = "adr_invalid"
ADR_FAILED = "adr_failed"
ADR_STATE_UPDATED = "adr_state_updated"
MA_CONTEXT_UPDATED = "ma_context_updated"
MA_CONTEXT_PARTIAL = "ma_context_partial"
MA_CONTEXT_INVALID = "ma_context_invalid"
MA_CONTEXT_FAILED = "ma_context_failed"
MA_CONTEXT_STATE_UPDATED = "ma_context_state_updated"
MOMENTUM_CONTEXT_UPDATED = "momentum_context_updated"
MOMENTUM_CONTEXT_PARTIAL = "momentum_context_partial"
MOMENTUM_CONTEXT_INVALID = "momentum_context_invalid"
MOMENTUM_CONTEXT_FAILED = "momentum_context_failed"
MOMENTUM_CONTEXT_STATE_UPDATED = "momentum_context_state_updated"
VOLUME_CONTEXT_UPDATED = "volume_context_updated"
VOLUME_CONTEXT_PARTIAL = "volume_context_partial"
VOLUME_CONTEXT_INVALID = "volume_context_invalid"
VOLUME_CONTEXT_FAILED = "volume_context_failed"
VOLUME_CONTEXT_STATE_UPDATED = "volume_context_state_updated"
MULTI_TIMEFRAME_EVIDENCE_UPDATED = "multi_timeframe_evidence_updated"
MULTI_TIMEFRAME_EVIDENCE_PARTIAL = "multi_timeframe_evidence_partial"
MULTI_TIMEFRAME_EVIDENCE_INVALID = "multi_timeframe_evidence_invalid"
MULTI_TIMEFRAME_EVIDENCE_FAILED = "multi_timeframe_evidence_failed"
MULTI_TIMEFRAME_EVIDENCE_STATE_UPDATED = "multi_timeframe_evidence_state_updated"

# ==================================================
# Market Context Events
# ==================================================

MARKET_CONTEXT_UPDATED = "market_context_updated"
MARKET_CONTEXT_V2_UPDATED = "market_context_v2_updated"
MARKET_CONTEXT_V2_READY = "market_context_v2_ready"

# ==================================================
# Price Action Events
# ==================================================

PRICE_ACTION_READY = "price_action_ready"

# ==================================================
# Option Chain Events
# ==================================================

OPTION_CHAIN_UPDATED = "option_chain_updated"
OPTION_CHAIN_READY = "option_chain_ready"

# ==================================================
# AI Events
# ==================================================

AI_DECISION_READY = "ai_decision_ready"
AI_REASONING_V2_UPDATED = "ai_reasoning_v2_updated"
AI_REASONING_V2_READY = "ai_reasoning_v2_ready"
AI_CONFIDENCE_CALIBRATED = "ai_confidence_calibrated"
AI_CONFIDENCE_BLOCKED = "ai_confidence_blocked"
AI_CONFIDENCE_REDUCED = "ai_confidence_reduced"
AI_CONFIDENCE_STATE_UPDATED = "ai_confidence_state_updated"
AI_CONFIDENCE_FAILED = "ai_confidence_failed"

# ==================================================
# TradingView Evidence Mapping Events
# ==================================================

TRADINGVIEW_EVIDENCE_MAPPED = "tradingview_evidence_mapped"
TRADINGVIEW_EVIDENCE_PARTIAL = "tradingview_evidence_partial"
TRADINGVIEW_EVIDENCE_INVALID = "tradingview_evidence_invalid"
TRADINGVIEW_EVIDENCE_STATE_UPDATED = "tradingview_evidence_state_updated"
TRADINGVIEW_EVIDENCE_FAILED = "tradingview_evidence_failed"

# ==================================================
# Strategy Events
# ==================================================

STRATEGY_DECISION_READY = "strategy_decision_ready"
STRATEGY_DECISION_V2_UPDATED = "strategy_decision_v2_updated"
STRATEGY_DECISION_V2_READY = "strategy_decision_v2_ready"

# ==================================================
# Risk Management Events
# ==================================================

RISK_UPDATED = "risk_updated"
RISK_MANAGEMENT_V2_UPDATED = "risk_management_v2_updated"
RISK_MANAGEMENT_V2_READY = "risk_management_v2_ready"
RISK_EVALUATED = "risk_evaluated"
RISK_APPROVED = "risk_approved"
RISK_REJECTED = "risk_rejected"
RISK_LOCKED = "risk_locked"
RISK_STATE_UPDATED = "risk_state_updated"
RISK_SESSION_RESET = "risk_session_reset"
RISK_MANUAL_LOCKED = "risk_manual_locked"
RISK_EMERGENCY_LOCKED = "risk_emergency_locked"

# ==================================================
# Execution Runtime Events
# ==================================================

EXECUTION_RUNTIME_V1_UPDATED = "execution_runtime_v1_updated"
EXECUTION_INTENT_CREATED = "execution_intent_created"
EXECUTION_DRY_RUN_SUBMITTED = "execution_dry_run_submitted"
EXECUTION_DRY_RUN_ACKNOWLEDGED = "execution_dry_run_acknowledged"
EXECUTION_DRY_RUN_PARTIALLY_FILLED = "execution_dry_run_partially_filled"
EXECUTION_DRY_RUN_FILLED = "execution_dry_run_filled"
EXECUTION_DRY_RUN_CANCELLED = "execution_dry_run_cancelled"
EXECUTION_DRY_RUN_REJECTED = "execution_dry_run_rejected"

# ==================================================
# Trade Execution Policy Events
# ==================================================

EXECUTION_POLICY_EVALUATED = "execution_policy_evaluated"
EXECUTION_PLAN_PREPARED = "execution_plan_prepared"
EXECUTION_PLAN_REJECTED = "execution_plan_rejected"
EXECUTION_PLAN_LOCKED = "execution_plan_locked"
EXECUTION_PLAN_APPROVED = "execution_plan_approved"
EXECUTION_PLAN_CANCELLED = "execution_plan_cancelled"
EXECUTION_PLAN_EXPIRED = "execution_plan_expired"
EXECUTION_POLICY_STATE_UPDATED = "execution_policy_state_updated"

# ==================================================
# Trade Decision Authorization Events
# ==================================================

TRADE_AUTHORIZATION_COMPLETED = "trade_authorization_completed"
TRADE_AUTHORIZATION_APPROVED = "trade_authorization_approved"
TRADE_AUTHORIZATION_REDUCED = "trade_authorization_reduced"
TRADE_AUTHORIZATION_BLOCKED = "trade_authorization_blocked"
TRADE_AUTHORIZATION_STATE_UPDATED = "trade_authorization_state_updated"
TRADE_AUTHORIZATION_FAILED = "trade_authorization_failed"

# ==================================================
# Paper Execution Coordinator Events
# ==================================================

PAPER_EXECUTION_COORDINATOR_STATE_UPDATED = "paper_execution_coordinator_state_updated"
PAPER_EXECUTION_EVALUATED = "paper_execution_evaluated"
PAPER_EXECUTION_ACCEPTED = "paper_execution_accepted"
PAPER_EXECUTION_REJECTED = "paper_execution_rejected"
PAPER_EXECUTION_DUPLICATE = "paper_execution_duplicate"
PAPER_ENTRY_ORDER_CREATED = "paper_entry_order_created"
PAPER_ENTRY_SUBMITTED = "paper_entry_submitted"
PAPER_ENTRY_PARTIALLY_FILLED = "paper_entry_partially_filled"
PAPER_ENTRY_FILLED = "paper_entry_filled"
PAPER_PROTECTIVE_ORDERS_CREATED = "paper_protective_orders_created"
PAPER_EXECUTION_CANCELLED = "paper_execution_cancelled"
PAPER_EXECUTION_COMPLETED = "paper_execution_completed"
PAPER_EXECUTION_FAILED = "paper_execution_failed"

# ==================================================
# Authorized Paper Execution Handoff Events
# ==================================================

AUTHORIZED_PAPER_HANDOFF_COMPLETED = "authorized_paper_handoff_completed"
AUTHORIZED_PAPER_HANDOFF_EXECUTED = "authorized_paper_handoff_executed"
AUTHORIZED_PAPER_HANDOFF_HELD = "authorized_paper_handoff_held"
AUTHORIZED_PAPER_HANDOFF_REJECTED = "authorized_paper_handoff_rejected"
AUTHORIZED_PAPER_HANDOFF_STATE_UPDATED = "authorized_paper_handoff_state_updated"
AUTHORIZED_PAPER_HANDOFF_FAILED = "authorized_paper_handoff_failed"

# ==================================================
# Execution Reconciliation Events
# ==================================================

EXECUTION_RECONCILIATION_STATE_UPDATED = "execution_reconciliation_state_updated"
EXECUTION_RECONCILIATION_STARTED = "execution_reconciliation_started"
EXECUTION_RECONCILIATION_COMPLETED = "execution_reconciliation_completed"
EXECUTION_RECONCILIATION_WARNING = "execution_reconciliation_warning"
EXECUTION_RECONCILIATION_INCONSISTENT = "execution_reconciliation_inconsistent"
EXECUTION_RECONCILIATION_INVALID = "execution_reconciliation_invalid"
EXECUTION_RECONCILIATION_FAILED = "execution_reconciliation_failed"

# ==================================================
# Shadow Trading Session Events
# ==================================================

SHADOW_SESSION_STATE_UPDATED = "shadow_session_state_updated"
SHADOW_SESSION_STARTED = "shadow_session_started"
SHADOW_SESSION_OBSERVATION_RECORDED = "shadow_session_observation_recorded"
SHADOW_SESSION_COMPLETED = "shadow_session_completed"
SHADOW_SESSION_WARNING = "shadow_session_warning"
SHADOW_SESSION_DEGRADED = "shadow_session_degraded"
SHADOW_SESSION_FAILED = "shadow_session_failed"

# ==================================================
# Zerodha Read-Only Connectivity Events
# ==================================================

ZERODHA_CONNECTION_STATE_UPDATED = "zerodha_connection_state_updated"
ZERODHA_CONNECTED = "zerodha_connected"
ZERODHA_DISCONNECTED = "zerodha_disconnected"
ZERODHA_AUTHENTICATION_FAILED = "zerodha_authentication_failed"
ZERODHA_SUBSCRIPTION_UPDATED = "zerodha_subscription_updated"
ZERODHA_TICK_REJECTED = "zerodha_tick_rejected"
ZERODHA_CONNECTION_FAILED = "zerodha_connection_failed"

# ==================================================
# Live Shadow Market Session Events
# ==================================================

LIVE_SHADOW_SESSION_STATE_UPDATED = "live_shadow_session_state_updated"
LIVE_SHADOW_SESSION_STARTED = "live_shadow_session_started"
LIVE_SHADOW_TICK_OBSERVED = "live_shadow_tick_observed"
LIVE_SHADOW_SESSION_WARNING = "live_shadow_session_warning"
LIVE_SHADOW_SESSION_DEGRADED = "live_shadow_session_degraded"
LIVE_SHADOW_SESSION_FAILED = "live_shadow_session_failed"
LIVE_SHADOW_SESSION_COMPLETED = "live_shadow_session_completed"

# ==================================================
# Order Management Events
# ==================================================

ORDER_PLACED = "order_placed"
ORDER_MODIFIED = "order_modified"
ORDER_CANCELLED = "order_cancelled"
ORDER_FILLED = "order_filled"
ORDER_REJECTED = "order_rejected"

# ==================================================
# Position Events
# ==================================================

POSITION_OPENED = "position_opened"
POSITION_UPDATED = "position_updated"
POSITION_CLOSED = "position_closed"
POSITION_MANAGEMENT_V1_UPDATED = "position_management_v1_updated"
POSITION_OPENED_DRY_RUN = "position_opened_dry_run"
POSITION_PRICE_UPDATED = "position_price_updated"
POSITION_PARTIALLY_CLOSED_DRY_RUN = "position_partially_closed_dry_run"
POSITION_CLOSED_DRY_RUN = "position_closed_dry_run"
POSITION_INVALIDATED_DRY_RUN = "position_invalidated_dry_run"
POSITION_OBJECTIVE_REACHED = "position_objective_reached"

# ==================================================
# Paper Trading Events
# ==================================================

PAPER_ORDER_CREATED = "paper_order_created"
PAPER_ORDER_TRIGGERED = "paper_order_triggered"
PAPER_ORDER_CANCELLED = "paper_order_cancelled"
PAPER_ORDER_EXPIRED = "paper_order_expired"
PAPER_POSITION_OPENED = "paper_position_opened"
PAPER_POSITION_UPDATED = "paper_position_updated"
PAPER_POSITION_CLOSED = "paper_position_closed"
PAPER_TRADE_RECORDED = "paper_trade_recorded"

# ==================================================
# Trade Lifecycle Events
# ==================================================

TRADE_LIFECYCLE_V1_UPDATED = "trade_lifecycle_v1_updated"
TRADE_LIFECYCLE_V1_READY = "trade_lifecycle_v1_ready"
TRADE_LIFECYCLE_STAGE_CHANGED = "trade_lifecycle_stage_changed"
TRADE_LIFECYCLE_BLOCKED = "trade_lifecycle_blocked"
TRADE_LIFECYCLE_POSITION_OPENED = "trade_lifecycle_position_opened"
TRADE_LIFECYCLE_POSITION_CLOSED = "trade_lifecycle_position_closed"
TRADE_LIFECYCLE_RUNTIME_INTEGRATION_V1_UPDATED = "trade_lifecycle_runtime_integration_v1_updated"
TRADE_LIFECYCLE_RUNTIME_INTEGRATION_V1_READY = "trade_lifecycle_runtime_integration_v1_ready"
TRADE_LIFECYCLE_CONTEXT_ROUTED = "trade_lifecycle_context_routed"
TRADE_LIFECYCLE_POSITION_PRICE_ROUTED = "trade_lifecycle_position_price_routed"
TRADE_LIFECYCLE_RUNTIME_INTEGRATION_ERROR = "trade_lifecycle_runtime_integration_error"

# ==================================================
# Trade Journal Events
# ==================================================

TRADE_RECORDED = "trade_recorded"
TRADE_JOURNAL_V1_UPDATED = "trade_journal_v1_updated"
TRADE_JOURNAL_ENTRY_RECORDED = "trade_journal_entry_recorded"
TRADE_JOURNAL_DUPLICATE_SUPPRESSED = "trade_journal_duplicate_suppressed"
TRADE_PERFORMANCE_ANALYTICS_UPDATED = "trade_performance_analytics_updated"
TRADE_JOURNAL_RUNTIME_INTEGRATION_V1_UPDATED = "trade_journal_runtime_integration_v1_updated"
TRADE_JOURNAL_RUNTIME_INTEGRATION_V1_READY = "trade_journal_runtime_integration_v1_ready"
TRADE_JOURNAL_LIFECYCLE_ROUTED = "trade_journal_lifecycle_routed"
TRADE_JOURNAL_TRADE_RECORDED = "trade_journal_trade_recorded"
TRADE_JOURNAL_RUNTIME_INTEGRATION_ERROR = "trade_journal_runtime_integration_error"

# ==================================================
# Performance Analytics Events
# ==================================================

PERFORMANCE_TRADE_ACCEPTED = "performance_trade_accepted"
PERFORMANCE_ANALYTICS_UPDATED = "performance_analytics_updated"
PERFORMANCE_EXPORT_COMPLETED = "performance_export_completed"
PERFORMANCE_EXPORT_FAILED = "performance_export_failed"

# ==================================================
# Alert & Notification Events
# ==================================================

VOICE_ALERT = "voice_alert"
NOTIFICATION = "notification"

# ==================================================
# System Events
# ==================================================

SYSTEM_STARTED = "system_started"
SYSTEM_STOPPED = "system_stopped"
SYSTEM_ERROR = "system_error"

# ==================================================
# Production Safety Events
# ==================================================

PRODUCTION_SAFETY_V1_UPDATED = "production_safety_v1_updated"
PRODUCTION_SAFETY_V1_READY = "production_safety_v1_ready"
PRODUCTION_SAFETY_V1_DEGRADED = "production_safety_v1_degraded"
PRODUCTION_SAFETY_V1_LOCKED = "production_safety_v1_locked"
PRODUCTION_SAFETY_INCIDENT_OPENED = "production_safety_incident_opened"
PRODUCTION_SAFETY_INCIDENT_RESOLVED = "production_safety_incident_resolved"
PRODUCTION_SAFETY_RECOVERY_PENDING = "production_safety_recovery_pending"
PRODUCTION_SAFETY_RECOVERED = "production_safety_recovered"
PRODUCTION_SAFETY_ERROR = "production_safety_error"

# ==================================================
# Live Market Validation Events
# ==================================================

LIVE_VALIDATION_SESSION_STARTED = "live_validation_session_started"
LIVE_VALIDATION_UPDATED = "live_validation_updated"
LIVE_VALIDATION_FINDING = "live_validation_finding"
LIVE_VALIDATION_SESSION_COMPLETED = "live_validation_session_completed"
LIVE_VALIDATION_SESSION_FAILED = "live_validation_session_failed"

# ==================================================
# Historical Market Replay Events
# ==================================================

HISTORICAL_REPLAY_LOADED = "historical_replay_loaded"
HISTORICAL_REPLAY_STARTED = "historical_replay_started"
HISTORICAL_REPLAY_PAUSED = "historical_replay_paused"
HISTORICAL_REPLAY_RESUMED = "historical_replay_resumed"
HISTORICAL_REPLAY_PROGRESS_UPDATED = "historical_replay_progress_updated"
HISTORICAL_REPLAY_COMPLETED = "historical_replay_completed"
HISTORICAL_REPLAY_STOPPED = "historical_replay_stopped"
HISTORICAL_REPLAY_FAILED = "historical_replay_failed"

# ==================================================
# Deterministic Backtest Events
# ==================================================

BACKTEST_READY = "backtest_ready"
BACKTEST_STARTED = "backtest_started"
BACKTEST_SESSION_STARTED = "backtest_session_started"
BACKTEST_SESSION_COMPLETED = "backtest_session_completed"
BACKTEST_SESSION_FAILED = "backtest_session_failed"
BACKTEST_PAUSED = "backtest_paused"
BACKTEST_RESUMED = "backtest_resumed"
BACKTEST_STOPPED = "backtest_stopped"
BACKTEST_COMPLETED = "backtest_completed"
BACKTEST_FAILED = "backtest_failed"
BACKTEST_UPDATED = "backtest_updated"
