"""
Momentum Context Engine V1 enums.
"""

from enum import Enum


class MomentumDirection(Enum):
    RISING = "rising"
    FALLING = "falling"
    FLAT = "flat"


class MomentumStrength(Enum):
    WEAK = "weak"
    NORMAL = "normal"
    STRONG = "strong"
    EXTREME = "extreme"


class MomentumAcceleration(Enum):
    ACCELERATING = "accelerating"
    DECELERATING = "decelerating"
    STABLE = "stable"


class MomentumState(Enum):
    ACCELERATING = "accelerating"
    DECELERATING = "decelerating"
    REVERSING = "reversing"
    STABLE = "stable"
