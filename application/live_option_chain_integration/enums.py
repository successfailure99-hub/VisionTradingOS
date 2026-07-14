"""
Live option-chain integration enums.
"""

from enum import Enum


class LiveOptionChainIntegrationStatus(str, Enum):
    CREATED = "created"
    VALIDATING = "validating"
    READY = "ready"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    CLEARED = "cleared"


class LiveOptionChainDeliveryKind(str, Enum):
    UNDERLYING_PRICE = "underlying_price"
    OPTION_TICK_BATCH = "option_tick_batch"
