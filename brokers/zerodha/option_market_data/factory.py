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
        return ZerodhaOptionMarketDataSubscriptionManager(transport=transport, clock=clock)
