"""
Build-up classifier for sequential option-chain analytics.
"""

from engines.option_chain_analytics.configuration import OptionChainAnalyticsConfiguration
from engines.option_chain_analytics.enums import OptionBuildUpType


class OptionBuildUpClassifier:
    def classify(
        self,
        *,
        current_price: float,
        previous_price: float | None,
        runtime_change_open_interest: int,
        previous_open_interest: int | None,
        current_open_interest: int,
        configuration: OptionChainAnalyticsConfiguration,
    ) -> OptionBuildUpType:
        if not isinstance(configuration, OptionChainAnalyticsConfiguration):
            raise TypeError("configuration must be OptionChainAnalyticsConfiguration")
        if previous_price is None or previous_open_interest is None:
            return OptionBuildUpType.INSUFFICIENT_DATA

        price_delta = float(current_price) - float(previous_price)
        oi_delta = int(current_open_interest) - int(previous_open_interest)

        if abs(price_delta) < configuration.minimum_price_change:
            return OptionBuildUpType.NEUTRAL
        if abs(oi_delta) < configuration.minimum_oi_change:
            return OptionBuildUpType.NEUTRAL

        if price_delta > 0 and oi_delta > 0:
            return OptionBuildUpType.LONG_BUILDUP
        if price_delta < 0 and oi_delta > 0:
            return OptionBuildUpType.SHORT_BUILDUP
        if price_delta < 0 and oi_delta < 0:
            return OptionBuildUpType.LONG_UNWINDING
        if price_delta > 0 and oi_delta < 0:
            return OptionBuildUpType.SHORT_COVERING
        return OptionBuildUpType.NEUTRAL
