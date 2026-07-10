"""
====================================================
Vision Trading OS
File: market/models/instrument_info.py
====================================================

Defines immutable metadata for supported trading
instruments.

This module provides a single source of truth for
instrument-specific information used throughout
Vision Trading OS.

Author : Vision Trading OS
"""

from __future__ import annotations

from dataclasses import dataclass

from market.enums.exchange import Exchange
from market.enums.instrument import Instrument


@dataclass(frozen=True, slots=True)
class InstrumentInfo:
    """
    Immutable metadata describing a trading instrument.
    """

    instrument: Instrument

    exchange: Exchange

    trading_symbol: str

    display_name: str

    lot_size: int

    tick_size: float

    price_precision: int = 2

    def round_price(self, price: float) -> float:
        """
        Round a price according to the configured
        precision.
        """

        return round(price, self.price_precision)

    def ticks_between(
        self,
        price1: float,
        price2: float,
    ) -> int:
        """
        Number of minimum ticks between two prices.
        """

        difference = abs(price2 - price1)

        return round(difference / self.tick_size)


# -----------------------------------------------------
# Instrument Registry
# -----------------------------------------------------

INSTRUMENTS: dict[Instrument, InstrumentInfo] = {

    Instrument.NIFTY: InstrumentInfo(
        instrument=Instrument.NIFTY,
        exchange=Exchange.NSE,
        trading_symbol="NIFTY",
        display_name="NIFTY 50",
        lot_size=75,
        tick_size=0.05,
    ),

    Instrument.BANKNIFTY: InstrumentInfo(
        instrument=Instrument.BANKNIFTY,
        exchange=Exchange.NSE,
        trading_symbol="BANKNIFTY",
        display_name="BANK NIFTY",
        lot_size=35,
        tick_size=0.05,
    ),

    Instrument.FINNIFTY: InstrumentInfo(
        instrument=Instrument.FINNIFTY,
        exchange=Exchange.NSE,
        trading_symbol="FINNIFTY",
        display_name="FIN NIFTY",
        lot_size=65,
        tick_size=0.05,
    ),

    Instrument.MIDCPNIFTY: InstrumentInfo(
        instrument=Instrument.MIDCPNIFTY,
        exchange=Exchange.NSE,
        trading_symbol="MIDCPNIFTY",
        display_name="MIDCAP NIFTY",
        lot_size=120,
        tick_size=0.05,
    ),

    Instrument.SBI: InstrumentInfo(
        instrument=Instrument.SBI,
        exchange=Exchange.NSE,
        trading_symbol="SBIN",
        display_name="State Bank of India",
        lot_size=750,
        tick_size=0.05,
    ),

    Instrument.ICICI_BANK: InstrumentInfo(
        instrument=Instrument.ICICI_BANK,
        exchange=Exchange.NSE,
        trading_symbol="ICICIBANK",
        display_name="ICICI Bank",
        lot_size=700,
        tick_size=0.05,
    ),

    Instrument.AXIS_BANK: InstrumentInfo(
        instrument=Instrument.AXIS_BANK,
        exchange=Exchange.NSE,
        trading_symbol="AXISBANK",
        display_name="Axis Bank",
        lot_size=625,
        tick_size=0.05,
    ),
}


def get_instrument_info(
    instrument: Instrument,
) -> InstrumentInfo:
    """
    Retrieve metadata for an instrument.

    Raises
    ------
    KeyError
        If the instrument is unsupported.
    """

    return INSTRUMENTS[instrument]