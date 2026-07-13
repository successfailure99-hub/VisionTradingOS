"""
No-network integration for Zerodha historical data.
"""

from datetime import UTC, datetime, timedelta

from application import ApplicationBootstrap
from brokers.zerodha.historical import ZerodhaHistoricalDataManager
from brokers.zerodha.instruments import ZerodhaIndexSubscriptionResolver, ZerodhaInstrumentCatalogue, ZerodhaInstrumentRecord, ZerodhaInstrumentType
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


class FakeHistoricalClient:
    def __init__(self):
        self.calls = []

    def historical_data(self, **kwargs):
        self.calls.append(kwargs)
        return [
            dict(date=NOW, open=1, high=2, low=1, close=1.5, volume=10),
            dict(date=NOW + timedelta(minutes=10), open=2, high=3, low=2, close=2.5, volume=20),
            dict(date=NOW + timedelta(minutes=10), open=2, high=3, low=2, close=2.5, volume=20),
        ]


def test_resolved_nifty_historical_fetch_no_network_or_runtime_side_effects():
    record = ZerodhaInstrumentRecord(12345, 1, "NIFTY 50", "NIFTY 50", Exchange.NSE, "INDICES", ZerodhaInstrumentType.INDEX, None, 0.0, 1, 0.05)
    resolution = ZerodhaIndexSubscriptionResolver(ZerodhaInstrumentCatalogue((record,))).resolve(Instrument.NIFTY)
    client = FakeHistoricalClient()
    manager = ZerodhaHistoricalDataManager(client=client, clock=lambda: NOW)
    result = manager.fetch_resolution(resolution, timeframe=TimeFrame.FIVE_MINUTES, start_at=NOW, end_at=NOW + timedelta(minutes=15))
    assert client.calls[0]["instrument_token"] == 12345
    assert all(isinstance(candle, Candle) for candle in result.candles)
    assert [candle.symbol for candle in result.candles] == ["NIFTY", "NIFTY"]
    assert [candle.timeframe for candle in result.candles] == ["5m", "5m"]
    assert result.duplicate_count == 1
    assert result.gaps
    lifecycle = ApplicationBootstrap().create_application()
    snapshot = lifecycle.snapshot().orchestrator_snapshot
    assert snapshot.safety_mode.value == "analysis_only"
    assert snapshot.broker_mode.value == "dry_run"
    assert not hasattr(client, "connect")
    assert not hasattr(client, "submitted_orders")
