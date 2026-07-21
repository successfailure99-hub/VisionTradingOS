"""
TradingView Evidence Mapping Engine V1 enumerations.
"""

from enum import Enum


class EvidenceAvailability(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    INVALID = "invalid"
    STALE = "stale"


class PriceLocation(str, Enum):
    ABOVE = "above"
    BELOW = "below"
    AT = "at"
    INSIDE = "inside"
    UNKNOWN = "unknown"


class CamarillaRegion(str, Enum):
    ABOVE_H6 = "above_h6"
    H5_H6 = "h5_h6"
    H4_H5 = "h4_h5"
    H3_H4 = "h3_h4"
    L3_H3 = "l3_h3"
    L4_L3 = "l4_l3"
    L5_L4 = "l5_l4"
    L6_L5 = "l6_l5"
    BELOW_L6 = "below_l6"
    UNKNOWN = "unknown"


class CPRRegion(str, Enum):
    ABOVE_CPR = "above_cpr"
    INSIDE_CPR = "inside_cpr"
    BELOW_CPR = "below_cpr"
    UNKNOWN = "unknown"


class TradingViewEvidenceLifecycle(str, Enum):
    CREATED = "created"
    READY = "ready"
    ACTIVE = "active"
    STOPPED = "stopped"
    FAILED = "failed"
