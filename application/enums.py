"""
Application Orchestrator V1 enumerations.
"""

from enum import Enum


class ApplicationMode(str, Enum):
    ANALYSIS_ONLY = "analysis_only"
    DRY_RUN = "dry_run"


class OrchestratorAction(str, Enum):
    MARKET_CONTEXT = "market_context"
    AI_REASONING = "ai_reasoning"
    STRATEGY = "strategy"
    RISK = "risk"
    ORDER_CREATED = "order_created"
    BROKER_DRY_RUN = "broker_dry_run"
    POSITION_UPDATED = "position_updated"
    TRADE_RECORDED = "trade_recorded"


class OrchestratorStatus(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
