from engines.option_chain_analytics import (
    OptionBuildUpClassifier,
    OptionBuildUpType,
    OptionChainAnalyticsConfiguration,
)


def classify(price, previous_price, oi, previous_oi):
    return OptionBuildUpClassifier().classify(
        current_price=price,
        previous_price=previous_price,
        runtime_change_open_interest=oi - (previous_oi or oi),
        previous_open_interest=previous_oi,
        current_open_interest=oi,
        configuration=OptionChainAnalyticsConfiguration(),
    )


def test_all_build_up_classifications_and_thresholds():
    assert classify(101, 100, 110, 100) is OptionBuildUpType.LONG_BUILDUP
    assert classify(99, 100, 110, 100) is OptionBuildUpType.SHORT_BUILDUP
    assert classify(99, 100, 90, 100) is OptionBuildUpType.LONG_UNWINDING
    assert classify(101, 100, 90, 100) is OptionBuildUpType.SHORT_COVERING
    assert classify(100.01, 100, 110, 100) is OptionBuildUpType.NEUTRAL
    assert classify(101, 100, 100, 100) is OptionBuildUpType.NEUTRAL
    assert classify(101, None, 110, None) is OptionBuildUpType.INSUFFICIENT_DATA
