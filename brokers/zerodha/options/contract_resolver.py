"""
Option pair and subscription-universe resolver.
"""

from datetime import UTC, datetime

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaSubscriptionMode
from brokers.zerodha.options.catalogue import ZerodhaOptionContractCatalogue
from brokers.zerodha.options.enums import ZerodhaDerivativeVenue, ZerodhaExpirySelection, ZerodhaOptionRight
from brokers.zerodha.options.expiry_resolver import ZerodhaOptionExpiryResolver
from brokers.zerodha.options.models import (
    ZerodhaExpiry,
    ZerodhaOptionPair,
    ZerodhaOptionUniverse,
    require_aware,
    require_supported_underlying,
    venue_for_underlying,
)
from brokers.zerodha.options.strike_resolver import ZerodhaOptionStrikeResolver
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


class ZerodhaOptionContractResolver:
    def __init__(self, catalogue: ZerodhaOptionContractCatalogue, *, clock=None):
        if not isinstance(catalogue, ZerodhaOptionContractCatalogue):
            raise TypeError("catalogue must be ZerodhaOptionContractCatalogue")
        self._catalogue = catalogue
        self._expiry_resolver = ZerodhaOptionExpiryResolver(catalogue)
        self._strike_resolver = ZerodhaOptionStrikeResolver(catalogue)
        self._clock = clock or (lambda: datetime.now(UTC))

    def resolve_pair(self, underlying: Instrument, *, expiry: ZerodhaExpiry, strike: float) -> ZerodhaOptionPair:
        require_supported_underlying(underlying)
        if not isinstance(expiry, ZerodhaExpiry):
            raise TypeError("expiry must be ZerodhaExpiry")
        calls = self._catalogue.contracts_for(underlying, expiry=expiry.expiry, strike=strike, right=ZerodhaOptionRight.CALL)
        puts = self._catalogue.contracts_for(underlying, expiry=expiry.expiry, strike=strike, right=ZerodhaOptionRight.PUT)
        if len(calls) != 1:
            raise ValueError("expected exactly one CE contract")
        if len(puts) != 1:
            raise ValueError("expected exactly one PE contract")
        return ZerodhaOptionPair(underlying=underlying, expiry=expiry, strike=strike, call=calls[0], put=puts[0])

    def resolve_universe(
        self,
        underlying: Instrument,
        *,
        as_of,
        underlying_price: float,
        expiry_selection: ZerodhaExpirySelection = ZerodhaExpirySelection.CURRENT,
        explicit_expiry=None,
        strikes_each_side: int = 5,
        mode: ZerodhaSubscriptionMode = ZerodhaSubscriptionMode.FULL,
    ) -> ZerodhaOptionUniverse:
        require_supported_underlying(underlying)
        if not isinstance(mode, ZerodhaSubscriptionMode):
            raise TypeError("mode must be ZerodhaSubscriptionMode")
        expiry = self._expiry_resolver.resolve(
            underlying,
            as_of=as_of,
            selection=expiry_selection,
            explicit_expiry=explicit_expiry,
        )
        strikes = self._strike_resolver.strike_window(
            underlying,
            expiry=expiry.expiry,
            underlying_price=underlying_price,
            strikes_each_side=strikes_each_side,
        )
        atm = self._strike_resolver.resolve_atm(underlying, expiry=expiry.expiry, underlying_price=underlying_price)
        step = self._strike_resolver.infer_strike_step(underlying, expiry=expiry.expiry)
        pairs = tuple(self.resolve_pair(underlying, expiry=expiry, strike=strike) for strike in strikes)
        subscriptions = []
        exchange = _project_exchange(venue_for_underlying(underlying))
        for pair in pairs:
            subscriptions.append(ZerodhaInstrumentSubscription(pair.call.instrument_token, underlying, exchange, mode))
            subscriptions.append(ZerodhaInstrumentSubscription(pair.put.instrument_token, underlying, exchange, mode))
        return ZerodhaOptionUniverse(
            underlying=underlying,
            venue=venue_for_underlying(underlying),
            expiry=expiry,
            underlying_price=underlying_price,
            atm_strike=atm,
            strike_step=step,
            pairs=pairs,
            subscriptions=tuple(subscriptions),
            resolved_at=require_aware(self._clock(), "clock result"),
        )


def _project_exchange(venue: ZerodhaDerivativeVenue) -> Exchange:
    if venue is ZerodhaDerivativeVenue.NFO:
        return Exchange.NSE
    if venue is ZerodhaDerivativeVenue.BFO:
        return Exchange.BSE
    raise ValueError("unsupported derivative venue")
