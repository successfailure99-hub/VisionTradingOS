"""
====================================================
Vision Trading OS
File: core/enums/exchange.py
====================================================

Defines all supported trading exchanges.

The Exchange enum uniquely identifies the exchange
on which an instrument is traded.

Author : Vision Trading OS
"""

from __future__ import annotations

from enum import Enum


class Exchange(str, Enum):
    """
    Supported trading exchanges.
    """

    # -------------------------------------------------
    # Indian Exchanges
    # -------------------------------------------------

    NSE = "NSE"

    BSE = "BSE"

    MCX = "MCX"

    NCDEX = "NCDEX"

    # -------------------------------------------------
    # International (Future Expansion)
    # -------------------------------------------------

    CME = "CME"

    NYSE = "NYSE"

    NASDAQ = "NASDAQ"

    # -------------------------------------------------
    # Properties
    # -------------------------------------------------

    @property
    def is_indian(self) -> bool:
        """
        Returns True if the exchange belongs to India.
        """

        return self in {
            Exchange.NSE,
            Exchange.BSE,
            Exchange.MCX,
            Exchange.NCDEX,
        }

    @property
    def is_international(self) -> bool:
        """
        Returns True if the exchange is outside India.
        """

        return not self.is_indian

    @classmethod
    def from_value(cls, value: str) -> "Exchange":
        """
        Convert a string into an Exchange enum.

        Parameters
        ----------
        value : str
            Exchange code.

        Raises
        ------
        ValueError
            If the exchange is unsupported.
        """

        normalized = value.strip().upper()

        for exchange in cls:
            if exchange.value == normalized:
                return exchange

        raise ValueError(f"Unsupported exchange: {value}")

    def __str__(self) -> str:
        """
        Human-readable representation.
        """

        return self.value