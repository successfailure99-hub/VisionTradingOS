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
