"""
Immutable Application Orchestrator V1 models.
"""

from dataclasses import dataclass
from typing import Any

from application.enums import ApplicationMode, OrchestratorAction, OrchestratorStatus


@dataclass(frozen=True, slots=True)
class OrchestratorResult:
    action: OrchestratorAction
    status: OrchestratorStatus
    mode: ApplicationMode
    payload: Any
    message: str
