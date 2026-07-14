"""
Factory for Live Option Chain Runtime V1.
"""

from application.live_option_chain.configuration import LiveOptionChainConfiguration
from application.live_option_chain.runtime import LiveOptionChainRuntime
from brokers.zerodha.option_market_data import ZerodhaOptionMarketDataSubscriptionManager
from brokers.zerodha.options import ZerodhaOptionUniverse
from engines.option_chain.option_chain_engine import OptionChainEngine


class LiveOptionChainRuntimeFactory:
    def create(
        self,
        *,
        universe: ZerodhaOptionUniverse,
        subscription_manager: ZerodhaOptionMarketDataSubscriptionManager,
        option_chain_engine: OptionChainEngine,
        configuration: LiveOptionChainConfiguration | None = None,
        clock=None,
    ) -> LiveOptionChainRuntime:
        return LiveOptionChainRuntime(
            universe=universe,
            subscription_manager=subscription_manager,
            option_chain_engine=option_chain_engine,
            configuration=configuration,
            clock=clock,
        )
