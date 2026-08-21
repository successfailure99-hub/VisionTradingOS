"""
Factory for option market-data subscription manager.
"""

from brokers.zerodha.market_data import ZerodhaTickerClientProtocol
from brokers.zerodha.option_market_data.manager import ZerodhaOptionMarketDataSubscriptionManager
from brokers.zerodha.option_market_data.transport import ZerodhaTickerOptionSubscriptionTransport


class ZerodhaOptionMarketDataSubscriptionManagerFactory:
    def create(
        self,
        *,
        client: ZerodhaTickerClientProtocol,
        clock=None,
    ) -> ZerodhaOptionMarketDataSubscriptionManager:
        transport = ZerodhaTickerOptionSubscriptionTransport(client)
        manager = ZerodhaOptionMarketDataSubscriptionManager(transport=transport, clock=clock)
        _register_reconnect_recovery(client, manager)
        return manager


def _register_reconnect_recovery(client, manager: ZerodhaOptionMarketDataSubscriptionManager) -> None:
    """Attach recovery to the shared raw ticker without coupling to the desktop router type."""
    candidate = client
    visited = set()
    while candidate is not None and id(candidate) not in visited:
        visited.add(id(candidate))
        register = getattr(candidate, "register_reconnect_recovery", None)
        if callable(register):
            register(manager.recover)
            return
        candidate = getattr(candidate, "_client", None)
