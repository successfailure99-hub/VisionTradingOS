import pytest

from engines.trade_journal_v1 import TradeJournalV1Configuration


def test_trade_journal_v1_configuration_defaults_and_validation():
    config = TradeJournalV1Configuration()

    assert config.minimum_trades_for_statistics == 5
    assert config.minimum_trades_for_trend == 10
    assert config.flat_pnl_tolerance == 0.0
    assert config.reject_duplicate_trade_ids is True
    assert not any("path" in field or "file" in field or "credential" in field for field in config.__dataclass_fields__)

    with pytest.raises(TypeError):
        TradeJournalV1Configuration(history_limit=True)
    with pytest.raises(ValueError):
        TradeJournalV1Configuration(equity_curve_limit=0)
    with pytest.raises(TypeError):
        TradeJournalV1Configuration(require_dry_run=1)
