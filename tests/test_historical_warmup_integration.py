"""
No-network Historical Warm-up integration tests.
"""

from datetime import UTC, datetime, timedelta

from application import ApplicationBootstrap
from application.historical_warmup import HistoricalWarmupCoordinator, HistoricalWarmupStatus
from brokers.zerodha.enums import BrokerExecutionMode
from brokers.zerodha.historical import ZerodhaHistoricalDataManager
from brokers.zerodha.instruments import ZerodhaInstrumentRecord, ZerodhaInstrumentResolution, ZerodhaInstrumentType
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.models.tick import Tick


TS = datetime(2026, 7, 10, 9, 15, tzinfo=UTC)


class FakeHistoricalClient:
    def __init__(self):
        self.calls = []
        self.responses = [
            [raw(-1440), raw(-1439), raw(-1438)],
            [raw(0), raw(1), raw(2)],
            [raw(-1440), raw(-1439), raw(-1438)],
            [raw(0), raw(1), raw(2)],
            [raw(3)],
        ]
        self.submitted_orders = []

    def historical_data(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def raw(offset=0, close=None):
    at = TS + timedelta(minutes=offset)
    return dict(date=at, open=100.0, high=104.0, low=98.0, close=close if close is not None else 101.0, volume=10)


def resolution():
    record = ZerodhaInstrumentRecord(101, 101, "NIFTY", "NIFTY", Exchange.NSE, "INDICES", ZerodhaInstrumentType.INDEX, None, 0.0, 1, 0.05)
    return ZerodhaInstrumentResolution(Instrument.NIFTY, record, ZerodhaInstrumentSubscription(101, Instrument.NIFTY, Exchange.NSE))


def test_no_network_warmup_daily_levels_idempotency_backfill_and_live_continuation():
    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    client = FakeHistoricalClient()
    manager = ZerodhaHistoricalDataManager(client=client, clock=lambda: TS)
    coordinator = HistoricalWarmupCoordinator(lifecycle=lifecycle, historical_manager=manager, resolutions=(resolution(),), clock=lambda: TS)
    first = coordinator.warm_up(
        start_at=TS,
        end_at=TS + timedelta(minutes=3),
        previous_day_start_at=TS - timedelta(days=1),
        previous_day_end_at=TS - timedelta(days=1, minutes=-3),
    )
    assert first.status is HistoricalWarmupStatus.READY
    snapshot = lifecycle.orchestrator.snapshot().runtime_snapshots[0]
    assert snapshot.cpr is not None
    assert snapshot.camarilla is not None
    assert snapshot.vwap is not None
    assert snapshot.vwap.cumulative_volume == 30
    assert snapshot.price_action is not None
    assert len(lifecycle.orchestrator.get_candle_history("NIFTY")) == 3

    second = coordinator.warm_up(
        start_at=TS,
        end_at=TS + timedelta(minutes=3),
        previous_day_start_at=TS - timedelta(days=1),
        previous_day_end_at=TS - timedelta(days=1, minutes=-3),
    )
    assert second.results[0].seed_result.accepted_count == 0
    backfill = coordinator.backfill(instrument=Instrument.NIFTY, end_at=TS + timedelta(minutes=4))
    assert backfill.results[0].seed_result.accepted_count == 1
    assert len(lifecycle.orchestrator.get_candle_history("NIFTY")) == 4

    tick = Tick(Instrument.NIFTY, Exchange.NSE, TS + timedelta(minutes=4, seconds=1), 105.0, 1, 104.0, 106.0, 0)
    live_snapshot = lifecycle.orchestrator.process_tick(tick)
    assert live_snapshot.latest_tick == tick
    assert live_snapshot.vwap is not None
    assert lifecycle.orchestrator.configuration.safety_mode.value == "analysis_only"
    assert lifecycle.orchestrator.broker_adapter.mode is BrokerExecutionMode.DRY_RUN
    assert lifecycle.orchestrator.snapshot().runtime_snapshots[0].latest_order is None
    assert client.submitted_orders == []
