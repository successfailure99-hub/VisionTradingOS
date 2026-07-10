"""
====================================================
Vision Trading OS
File: market/models/tick.py
====================================================

Immutable Tick model.

A Tick represents one market update received from
an exchange or broker feed.

This model is intentionally broker-independent and
serves as the canonical market data object used
throughout Vision Trading OS.

Author : Vision Trading OS
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from market.enums.exchange import Exchange
from market.enums.instrument import Instrument


@dataclass(frozen=True, slots=True)
class Tick:
    """
    Immutable market tick.
    """

    instrument: Instrument

    exchange: Exchange

    price: float

    volume: int

    exchange_timestamp: datetime

    received_timestamp: datetime

    bid: float | None = None

    ask: float | None = None

    bid_quantity: int | None = None

    ask_quantity: int | None = None

    open_interest: int | None = None

    sequence_number: int | None = None

    def __post_init__(self) -> None:
        """
        Validate tick values.
        """

        if self.price <= 0:
            raise ValueError("Price must be greater than zero.")

        if self.volume < 0:
            raise ValueError("Volume cannot be negative.")

        if (
            self.bid is not None
            and self.ask is not None
            and self.bid > self.ask
        ):
            raise ValueError(
                "Bid price cannot exceed ask price."
            )

    @property
    def spread(self) -> float | None:
        """
        Bid-Ask spread.
        """

        if self.bid is None or self.ask is None:
            return None

        return self.ask - self.bid

    @property
    def midpoint(self) -> float | None:
        """
        Mid-price between bid and ask.
        """

        if self.bid is None or self.ask is None:
            return None

        return (self.bid + self.ask) / 2

    @property
    def has_order_book(self) -> bool:
        """
        True when bid/ask prices are available.
        """

        return (
            self.bid is not None
            and self.ask is not None
        )

    @property
    def latency_ms(self) -> float:
        """
        Feed latency in milliseconds.
        """

        delta = (
            self.received_timestamp
            - self.exchange_timestamp
        )

        return delta.total_seconds() * 1000

    def __str__(self) -> str:
        """
        Human-readable representation.
        """

        return (
            f"{self.instrument.value} "
            f"{self.price:.2f} "
            f"Vol={self.volume}"
        )