from engines.option_chain_analytics import (
    OptionAnalyticsBias,
    OptionBuildUpType,
    OptionLevelMigration,
    OptionPressureType,
    OptionTrendDirection,
)


def test_enum_values():
    assert OptionBuildUpType.LONG_BUILDUP.value == "long_buildup"
    assert OptionPressureType.CALL_WRITING.value == "call_writing"
    assert OptionTrendDirection.RISING.value == "rising"
    assert OptionLevelMigration.SHIFTED_UP.value == "shifted_up"
    assert OptionAnalyticsBias.STRONGLY_BULLISH.value == "strongly_bullish"
