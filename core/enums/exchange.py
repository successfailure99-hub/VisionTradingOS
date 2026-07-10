"""
====================================================
Vision Trading OS
Exchange Enum
====================================================
"""

from enum import Enum


class Exchange(str, Enum):
    """
    Supported stock exchanges.
    """

    NSE = "NSE"

    BSE = "BSE"

    NFO = "NFO"

    CDS = "CDS"

    MCX = "MCX"