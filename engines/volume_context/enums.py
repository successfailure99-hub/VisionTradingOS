"""
Volume Context Engine V1 enums.
"""

from enum import Enum


class VolumeDirection(Enum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"


class VolumeStrength(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


class VolumeExpansionState(Enum):
    COMPRESSED = "compressed"
    NORMAL = "normal"
    EXPANDING = "expanding"
    CLIMACTIC = "climactic"


class VolumeExhaustionState(Enum):
    NORMAL = "normal"
    EXHAUSTED = "exhausted"
