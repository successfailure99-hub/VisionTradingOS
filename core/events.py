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

# ==================================================
# Strategy Events
# ==================================================

STRATEGY_DECISION_READY = "strategy_decision_ready"

# ==================================================
# Risk Management Events
# ==================================================

RISK_UPDATED = "risk_updated"

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