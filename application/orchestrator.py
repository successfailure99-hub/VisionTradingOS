"""
Application Orchestrator V1.
"""

from application.enums import ExecutionSafetyMode, RuntimeInstrument, RuntimeStatus
from application.models import OrchestratorSnapshot, RuntimeConfiguration, RuntimeSnapshot
from application.symbol_runtime import SymbolRuntime
from brokers.zerodha.adapter import ZerodhaBrokerAdapter
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick
from engines.market_data.market_data_engine import MarketDataEngine
from engines.order_management.models import OrderCommand, OrderSnapshot, OrderState
from engines.position.models import PositionFill, PositionMark
from engines.risk.models import RiskSnapshot
from engines.trade_journal.models import TradeJournalSnapshot
from engines.trade_journal.trade_journal_engine import TradeJournalEngine


class ApplicationOrchestrator:
    """
    Complete synchronous runtime owner for Application Orchestrator V1.

    Owns one shared MarketDataEngine, one shared TradeJournalEngine, one
    ZerodhaBrokerAdapter defaulting to DRY_RUN, and one SymbolRuntime per
    configured RuntimeInstrument. It is analysis-only by default and performs
    no live execution, authentication, credentials access, WebSockets,
    dashboard work, persistence, voice alerts, or background processing.
    """

    def __init__(
        self,
        event_bus,
        configuration: RuntimeConfiguration | None = None,
        *,
        broker_adapter: ZerodhaBrokerAdapter | None = None,
    ):
        self._event_bus = event_bus
        self._configuration = configuration or RuntimeConfiguration()
        if not isinstance(self._configuration, RuntimeConfiguration):
            raise ValueError("configuration must be a RuntimeConfiguration.")
        self._status = RuntimeStatus.CREATED
        self.market_data_engine = MarketDataEngine(event_bus)
        self.trade_journal_engine = TradeJournalEngine(event_bus)
        self.broker_adapter = broker_adapter or ZerodhaBrokerAdapter(mode=BrokerExecutionMode.DRY_RUN)
        if self.broker_adapter.mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("Application Orchestrator V1 requires a DRY_RUN Zerodha adapter by default.")
        self._runtimes = {
            instrument: SymbolRuntime(event_bus, self._configuration, instrument)
            for instrument in self._configuration.instruments
        }

    @property
    def configuration(self) -> RuntimeConfiguration:
        return self._configuration

    @property
    def status(self) -> RuntimeStatus:
        return self._status

    @property
    def runtimes(self) -> tuple[SymbolRuntime, ...]:
        return tuple(self._runtimes.values())

    def get_runtime(self, instrument: RuntimeInstrument) -> SymbolRuntime:
        self._validate_runtime_instrument(instrument)
        return self._runtimes[instrument]

    def start(self) -> OrchestratorSnapshot:
        for runtime in self._runtimes.values():
            runtime.start()
        self._status = RuntimeStatus.RUNNING
        return self.snapshot()

    def stop(self) -> OrchestratorSnapshot:
        for runtime in self._runtimes.values():
            runtime.stop()
        self._status = RuntimeStatus.STOPPED
        return self.snapshot()

    def process_tick(self, tick: Tick) -> dict[str, object]:
        self._require_running()
        accepted = self.market_data_engine.on_tick(tick)
        if accepted is None:
            return {"market_data": None, "runtime": None}
        runtime = self._runtime_for_core_instrument(tick.symbol)
        result = runtime.process_tick(tick)
        return {"market_data": accepted, "runtime": result}

    def process_daily_ohlc(self, instrument: RuntimeInstrument, daily_ohlc: DailyOHLC):
        self._require_running()
        return self.get_runtime(instrument).process_daily_ohlc(daily_ohlc)

    def process_option_chain(self, instrument: RuntimeInstrument, snapshot):
        self._require_running()
        return self.get_runtime(instrument).process_option_chain(snapshot)

    def build_market_context(self, instrument: RuntimeInstrument):
        self._require_running()
        return self.get_runtime(instrument).build_market_context()

    def run_ai_reasoning(self, instrument: RuntimeInstrument, context=None):
        self._require_running()
        return self.get_runtime(instrument).run_ai_reasoning(context)

    def run_strategy(self, instrument: RuntimeInstrument, context=None, reasoning=None):
        self._require_running()
        return self.get_runtime(instrument).run_strategy(context, reasoning)

    def run_risk(self, instrument: RuntimeInstrument, snapshot: RiskSnapshot):
        self._require_running()
        return self.get_runtime(instrument).run_risk(snapshot)

    def create_order(self, instrument: RuntimeInstrument, snapshot: OrderSnapshot) -> OrderState:
        self._require_running()
        return self.get_runtime(instrument).create_order(snapshot)

    def submit_order(self, order: OrderState):
        self._require_running()
        if self._configuration.safety_mode is not ExecutionSafetyMode.DRY_RUN:
            raise RuntimeError("Order submission is blocked unless safety mode is DRY_RUN.")
        if self.broker_adapter.mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("Order submission requires a DRY_RUN broker adapter.")
        return self.broker_adapter.place(order)

    def apply_order_command(self, instrument: RuntimeInstrument, command: OrderCommand) -> OrderState:
        self._require_running()
        return self.get_runtime(instrument).apply_order_command(command)

    def apply_position_fill(self, instrument: RuntimeInstrument, fill: PositionFill):
        self._require_running()
        return self.get_runtime(instrument).apply_position_fill(fill)

    def apply_position_mark(self, instrument: RuntimeInstrument, mark: PositionMark):
        self._require_running()
        return self.get_runtime(instrument).apply_position_mark(mark)

    def record_trade(self, snapshot: TradeJournalSnapshot):
        self._require_running()
        return self.trade_journal_engine.record(snapshot)

    def reset_symbol(self, instrument: RuntimeInstrument) -> RuntimeSnapshot:
        runtime = self.get_runtime(instrument)
        runtime.reset()
        if self._status is RuntimeStatus.RUNNING:
            runtime.start()
        return runtime.snapshot()

    def reset_all(self) -> OrchestratorSnapshot:
        self.market_data_engine.clear()
        self.trade_journal_engine.reset()
        for runtime in self._runtimes.values():
            runtime.reset()
        self._status = RuntimeStatus.CREATED
        return self.snapshot()

    def snapshot(self) -> OrchestratorSnapshot:
        return OrchestratorSnapshot(
            status=self._status,
            safety_mode=self._configuration.safety_mode,
            broker_mode=self.broker_adapter.mode,
            configured_instruments=self._configuration.instruments,
            shared_market_data_ready=self.market_data_engine.is_ready(),
            shared_trade_journal_ready=self.trade_journal_engine.is_ready(),
            runtime_snapshots=tuple(runtime.snapshot() for runtime in self._runtimes.values()),
        )

    def _runtime_for_core_instrument(self, instrument: Instrument) -> SymbolRuntime:
        runtime_instrument = RuntimeInstrument(instrument.value)
        return self.get_runtime(runtime_instrument)

    def _validate_runtime_instrument(self, instrument: RuntimeInstrument) -> None:
        if not isinstance(instrument, RuntimeInstrument):
            raise ValueError("instrument must be a RuntimeInstrument.")
        if instrument not in self._runtimes:
            raise ValueError("RuntimeInstrument is not configured.")

    def _require_running(self) -> None:
        if self._status is not RuntimeStatus.RUNNING:
            raise RuntimeError("ApplicationOrchestrator processing requires RUNNING status.")
