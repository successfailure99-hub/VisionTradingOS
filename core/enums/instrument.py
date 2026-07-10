"""
====================================================
Vision Trading OS
File: core/enums/instrument.py
====================================================

Defines all supported trading instruments.

This enum is used throughout the system to uniquely
identify the underlying instrument associated with
ticks, candles, option chains, and strategies.

Author : Vision Trading OS
"""

from __future__ import annotations

from enum import Enum


class Instrument(str, Enum):
    """
    Supported market instruments.

    The enum inherits from ``str`` so that values can
    be serialized directly to JSON, logs, databases,
    and message queues without additional conversion.
    """

    # -------------------------------------------------
    # Indexes
    # -------------------------------------------------

    NIFTY = "NIFTY"

    BANKNIFTY = "BANKNIFTY"

    FINNIFTY = "FINNIFTY"

    MIDCPNIFTY = "MIDCPNIFTY"

    SENSEX = "SENSEX"

    BANKEX = "BANKEX"

    # -------------------------------------------------
    # Individual Stocks
    # -------------------------------------------------

    SBI = "SBIN"

    ICICI_BANK = "ICICIBANK"

    AXIS_BANK = "AXISBANK"

    HDFC_BANK = "HDFCBANK"

    KOTAK_BANK = "KOTAKBANK"

    INDUSIND_BANK = "INDUSINDBK"

    # -------------------------------------------------
    # Utilities
    # -------------------------------------------------

    @classmethod
    def from_symbol(cls, symbol: str) -> "Instrument":
        """
        Convert a trading symbol into an Instrument.

        Parameters
        ----------
        symbol:
            NSE trading symbol.

        Raises
        ------
        ValueError
            If the symbol is not supported.
        """

        normalized = symbol.strip().upper()

        for instrument in cls:
            if instrument.value == normalized:
                return instrument

        raise ValueError(f"Unsupported instrument: {symbol}")

    @property
    def is_index(self) -> bool:
        """
        True if this instrument is an index.
        """

        return self in {
            Instrument.NIFTY,
            Instrument.BANKNIFTY,
            Instrument.FINNIFTY,
            Instrument.MIDCPNIFTY,
            Instrument.SENSEX,
            Instrument.BANKEX,
        }

    @property
    def is_stock(self) -> bool:
        """
        True if this instrument represents an equity.
        """

        return not self.is_index

    def __str__(self) -> str:
        """
        Human-readable representation.
        """

        return self.value