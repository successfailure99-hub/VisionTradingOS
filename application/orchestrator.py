"""
Application Orchestrator V1.
"""

from application.enums import ExecutionSafetyMode, RuntimeInstrument, RuntimeStatus
from application.models import OrchestratorSnapshot, RuntimeConfiguration, RuntimeSnapshot
from application.symbol_runtime import SymbolRuntime
from brokers.zerodha.adapter import ZerodhaBrokerAdapter
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick
from engines.market_data.market_data_engine import MarketDataEngine
from engines.order_management.models import OrderCommand, OrderRequest, OrderState
from engines.position.models import PositionFill, PositionMark
from engines.risk.models import AccountRiskState, RiskPolicy, TradeRiskPlan
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

    def get_runtime(self, instrument: str | RuntimeInstrument) -> SymbolRuntime:
        instrument = self._normalize_runtime_instrument(instrument)
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

    def process_tick(self, tick: Tick) -> RuntimeSnapshot:
        self._require_running()
        runtime = self._runtime_for_core_instrument(tick.symbol)
        accepted = self.market_data_engine.on_tick(tick)
        if accepted is None:
            return runtime.snapshot(self._latest_journal_record_for(runtime.instrument))
        runtime.process_tick(tick)
        return runtime.snapshot(self._latest_journal_record_for(runtime.instrument))

    def process_daily_ohlc(self, instrument: str | RuntimeInstrument, daily_ohlc: DailyOHLC):
        self._require_running()
        return self.get_runtime(instrument).process_daily_ohlc(daily_ohlc)

    def warm_up_candles(
        self,
        instrument: str | RuntimeInstrument,
        candles: tuple[Candle, ...],
        *,
        replace: bool = False,
    ) -> tuple[tuple[Candle, ...], RuntimeSnapshot]:
        self._require_running()
        runtime = self.get_runtime(instrument)
        accepted = runtime.warm_up_candles(candles, replace=replace)
        return accepted, runtime.snapshot(self._latest_journal_record_for(runtime.instrument))

    def get_candle_history(
        self,
        instrument: str | RuntimeInstrument,
    ) -> tuple[Candle, ...]:
        runtime = self.get_runtime(instrument)
        return runtime.get_candle_history()

    def process_option_chain(self, instrument: str | RuntimeInstrument, snapshot):
        self._require_running()
        return self.get_runtime(instrument).process_option_chain(snapshot)

    def build_market_context(
        self,
        instrument: str | RuntimeInstrument,
        *,
        timestamp,
        current_price: float,
        session_high: float,
        session_low: float,
    ):
        self._require_running()
        return self.get_runtime(instrument).build_market_context(
            timestamp=timestamp,
            current_price=current_price,
            session_high=session_high,
            session_low=session_low,
        )

    def run_ai_reasoning(self, instrument: str | RuntimeInstrument, context=None):
        self._require_running()
        return self.get_runtime(instrument).run_ai_reasoning(context)

    def run_strategy(self, instrument: str | RuntimeInstrument, context=None, reasoning=None):
        self._require_running()
        return self.get_runtime(instrument).run_strategy(context, reasoning)

    def run_risk(
        self,
        instrument: str | RuntimeInstrument,
        *,
        policy: RiskPolicy,
        account: AccountRiskState,
        trade_plan: TradeRiskPlan,
    ):
        self._require_running()
        return self.get_runtime(instrument).run_risk(
            policy=policy,
            account=account,
            trade_plan=trade_plan,
        )

    def create_order(self, instrument: str | RuntimeInstrument, request: OrderRequest) -> OrderState:
        self._require_running()
        return self.get_runtime(instrument).create_order(request)

    def submit_order(self, order: OrderState):
        self._require_running()
        if self._configuration.safety_mode is not ExecutionSafetyMode.DRY_RUN:
            raise RuntimeError("Order submission is blocked unless safety mode is DRY_RUN.")
        if self.broker_adapter.mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("Order submission requires a DRY_RUN broker adapter.")
        return self.broker_adapter.place(order)

    def apply_order_command(self, instrument: str | RuntimeInstrument, command: OrderCommand) -> OrderState:
        self._require_running()
        return self.get_runtime(instrument).apply_order_command(command)

    def apply_position_fill(self, instrument: str | RuntimeInstrument, fill: PositionFill):
        self._require_running()
        return self.get_runtime(instrument).apply_position_fill(fill)

    def apply_position_mark(self, instrument: str | RuntimeInstrument, mark: PositionMark):
        self._require_running()
        return self.get_runtime(instrument).apply_position_mark(mark)

    def record_trade(self, snapshot: TradeJournalSnapshot):
        self._require_running()
        instrument = self._normalize_runtime_instrument(snapshot.symbol)
        self._validate_runtime_instrument(instrument)
        return self.trade_journal_engine.record(snapshot)

    def reset_symbol(self, instrument: str | RuntimeInstrument) -> RuntimeSnapshot:
        runtime = self.get_runtime(instrument)
        runtime.reset()
        if self._status is RuntimeStatus.RUNNING:
            runtime.start()
        elif self._status is RuntimeStatus.STOPPED:
            runtime.stop()
        return runtime.snapshot()

    def reset_all(self) -> OrchestratorSnapshot:
        previous_status = self._status
        self.market_data_engine.clear()
        self.trade_journal_engine.reset()
        for runtime in self._runtimes.values():
            runtime.reset()
            if previous_status is RuntimeStatus.RUNNING:
                runtime.start()
            elif previous_status is RuntimeStatus.STOPPED:
                runtime.stop()
        self._status = previous_status
        return self.snapshot()

    def snapshot(self) -> OrchestratorSnapshot:
        return OrchestratorSnapshot(
            status=self._status,
            safety_mode=self._configuration.safety_mode,
            broker_mode=self.broker_adapter.mode,
            configured_instruments=self._configuration.instruments,
            shared_market_data_ready=self.market_data_engine.is_ready(),
            shared_trade_journal_ready=self.trade_journal_engine.is_ready(),
            runtime_snapshots=tuple(
                runtime.snapshot(self._latest_journal_record_for(runtime.instrument))
                for runtime in self._runtimes.values()
            ),
        )

    def _runtime_for_core_instrument(self, instrument: Instrument) -> SymbolRuntime:
        runtime_instrument = RuntimeInstrument(instrument.value)
        return self.get_runtime(runtime_instrument)

    def _normalize_runtime_instrument(self, instrument: str | RuntimeInstrument) -> RuntimeInstrument:
        if isinstance(instrument, RuntimeInstrument):
            return instrument
        if not isinstance(instrument, str):
            raise ValueError("instrument must be a RuntimeInstrument or symbol string.")
        normalized = instrument.strip().upper()
        if not normalized:
            raise ValueError("instrument symbol cannot be empty.")
        try:
            return RuntimeInstrument(normalized)
        except ValueError as exc:
            raise ValueError("Unsupported runtime instrument.") from exc

    def _validate_runtime_instrument(self, instrument: RuntimeInstrument) -> None:
        if not isinstance(instrument, RuntimeInstrument):
            raise ValueError("instrument must be a RuntimeInstrument.")
        if instrument not in self._runtimes:
            raise ValueError("RuntimeInstrument is not configured.")

    def _latest_journal_record_for(self, instrument: RuntimeInstrument):
        symbol = instrument.value
        for record in reversed(self.trade_journal_engine.get_records()):
            if record.symbol == symbol:
                return record
        return None

    def _require_running(self) -> None:
        if self._status is not RuntimeStatus.RUNNING:
            raise RuntimeError("ApplicationOrchestrator processing requires RUNNING status.")
