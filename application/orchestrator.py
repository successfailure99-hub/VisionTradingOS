"""
Application Orchestrator V1.
"""

from application.enums import ExecutionSafetyMode, RuntimeInstrument, RuntimeStatus
from application.models import OrchestratorSnapshot, RuntimeConfiguration, RuntimeSnapshot
from application.symbol_runtime import SymbolRuntime
from application.live_shadow_session import LiveShadowMarketSessionCoordinator, LiveShadowSessionRequest
from adapters.zerodha import ZerodhaCredentials, ZerodhaReadOnlyAdapter
from brokers.zerodha.adapter import ZerodhaBrokerAdapter
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick
from engines.ai_confidence_calibration.models import ConfidenceCalibrationRequest
from engines.market_data.market_data_engine import MarketDataEngine
from engines.order_management.models import OrderCommand, OrderRequest, OrderState
from engines.position.models import PositionFill, PositionMark
from engines.risk.models import AccountRiskState, RiskPolicy, TradeRiskPlan
from engines.paper_execution_coordinator.models import PaperExecutionReceipt, PaperExecutionRequest
from engines.execution_reconciliation.models import ExecutionReconciliationRequest, ExecutionReconciliationReport
from engines.shadow_trading_session.models import ShadowTradingSessionRequest
from engines.trade_decision_authorization.models import TradeAuthorizationRequest
from engines.trade_execution_policy.models import ExecutionRequest, TradeExecutionPlan
from engines.performance_analytics.engine import PerformanceAnalyticsEngine
from engines.deterministic_backtest.engine import DeterministicBacktestEngine
from engines.historical_market_replay import ReplayConfiguration, ReplayMode
from engines.historical_market_replay.engine import HistoricalMarketReplayEngine
from engines.live_market_validation.engine import LiveMarketValidationEngine
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
        zerodha_adapter: ZerodhaReadOnlyAdapter | None = None,
    ):
        self._event_bus = event_bus
        self._configuration = configuration or RuntimeConfiguration()
        if not isinstance(self._configuration, RuntimeConfiguration):
            raise ValueError("configuration must be a RuntimeConfiguration.")
        self._status = RuntimeStatus.CREATED
        self.market_data_engine = MarketDataEngine(event_bus)
        self.trade_journal_engine = TradeJournalEngine(event_bus)
        self.performance_analytics_engine = PerformanceAnalyticsEngine(
            configuration=self._configuration.performance_analytics_configuration,
            event_bus=event_bus,
        )
        self.live_validation_engine = LiveMarketValidationEngine(
            event_bus,
            configuration=self._configuration.live_validation_configuration,
        )
        replay_configuration = self._configuration.historical_replay_configuration
        if (
            self._configuration.deterministic_backtest_configuration is not None
            and self._configuration.deterministic_backtest_configuration.enabled
            and (replay_configuration is None or not replay_configuration.enabled)
        ):
            backtest = self._configuration.deterministic_backtest_configuration
            replay_configuration = ReplayConfiguration(
                enabled=backtest.enabled,
                mode=ReplayMode.ACCELERATED if backtest.enabled else ReplayMode.OFF,
                source_path=backtest.session_paths[0] if backtest.session_paths else None,
                speed_multiplier=1000.0,
                output_dir=backtest.output_directory / "replay",
                max_findings=backtest.max_findings,
                auto_load=False,
                auto_start=False,
            )
        self.historical_replay_engine = HistoricalMarketReplayEngine(
            event_bus,
            configuration=replay_configuration,
        )
        self.broker_adapter = broker_adapter or ZerodhaBrokerAdapter(mode=BrokerExecutionMode.DRY_RUN)
        if self.broker_adapter.mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("Application Orchestrator V1 requires a DRY_RUN Zerodha adapter by default.")
        self._runtimes = {
            instrument: SymbolRuntime(event_bus, self._configuration, instrument)
            for instrument in self._configuration.instruments
        }
        self.live_shadow_session_coordinator = LiveShadowMarketSessionCoordinator(event_bus, orchestrator=self)
        self.zerodha_adapter = zerodha_adapter or ZerodhaReadOnlyAdapter(event_bus, tick_consumer=self.process_live_zerodha_tick)
        self.deterministic_backtest_engine = DeterministicBacktestEngine(
            event_bus,
            configuration=self._configuration.deterministic_backtest_configuration,
            orchestrator=self,
        )

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
        replay_state = self.historical_replay_engine.snapshot().lifecycle_state.value
        if replay_state in {"running", "paused"}:
            self.historical_replay_engine.stop("Application shutdown stopped historical replay.")
        for runtime in self._runtimes.values():
            runtime.stop()
        self._status = RuntimeStatus.STOPPED
        return self.snapshot()

    def process_tick(self, tick: Tick, *, observe_shadow: bool = True) -> RuntimeSnapshot:
        snapshot, _, _ = self._process_tick_with_acceptance(tick, observe_shadow=observe_shadow)
        return snapshot

    def process_live_zerodha_tick(self, tick: Tick) -> RuntimeSnapshot:
        snapshot, accepted, authoritative_tick = self._process_tick_with_acceptance(tick, observe_shadow=False)
        self.live_shadow_session_coordinator.observe_tick(authoritative_tick, accepted=accepted)
        return snapshot

    def _process_tick_with_acceptance(self, tick: Tick, *, observe_shadow: bool) -> tuple[RuntimeSnapshot, bool, Tick]:
        self._require_running()
        runtime = self._runtime_for_core_instrument(tick.symbol)
        accepted_tick = self.market_data_engine.on_tick(tick)
        if accepted_tick is None:
            return runtime.snapshot(self._latest_journal_record_for(runtime.instrument)), False, tick
        runtime.process_tick(accepted_tick, observe_shadow=observe_shadow)
        return runtime.snapshot(self._latest_journal_record_for(runtime.instrument)), True, accepted_tick

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

    def calibrate_ai_confidence(self, instrument: str | RuntimeInstrument, request: ConfidenceCalibrationRequest):
        self._require_running()
        return self.get_runtime(instrument).calibrate_ai_confidence(request)

    def get_confidence_result(self, instrument: str | RuntimeInstrument, calibration_id: str):
        return self.get_runtime(instrument).get_confidence_result(calibration_id)

    def get_confidence_snapshot(self, instrument: str | RuntimeInstrument):
        return self.get_runtime(instrument).get_confidence_snapshot()

    def reset_confidence_calibration(self, instrument: str | RuntimeInstrument):
        return self.get_runtime(instrument).reset_confidence_calibration()

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

    def evaluate_execution_policy(self, instrument: str | RuntimeInstrument, request: ExecutionRequest) -> TradeExecutionPlan:
        self._require_running()
        return self.get_runtime(instrument).evaluate_execution_policy(request)

    def authorize_trade_decision(self, instrument: str | RuntimeInstrument, request: TradeAuthorizationRequest):
        self._require_running()
        runtime = self.get_runtime(instrument)
        if not isinstance(request, TradeAuthorizationRequest):
            raise TypeError("request must be TradeAuthorizationRequest")
        if request.instrument != runtime.instrument:
            raise ValueError("Trade authorization request instrument does not match runtime.")
        return runtime.authorize_trade_decision(request)

    def get_trade_authorization_result(self, instrument: str | RuntimeInstrument, authorization_id: str):
        return self.get_runtime(instrument).get_trade_authorization_result(authorization_id)

    def get_trade_authorization_snapshot(self, instrument: str | RuntimeInstrument):
        return self.get_runtime(instrument).get_trade_authorization_snapshot()

    def reset_trade_authorization(self, instrument: str | RuntimeInstrument):
        return self.get_runtime(instrument).reset_trade_authorization()

    def create_order_from_execution_plan(self, instrument: str | RuntimeInstrument, plan: TradeExecutionPlan) -> OrderState | None:
        self._require_running()
        return self.get_runtime(instrument).create_order_from_execution_plan(plan)

    def execute_paper_plan(self, instrument: str | RuntimeInstrument, request: PaperExecutionRequest) -> PaperExecutionReceipt:
        self._require_running()
        return self.get_runtime(instrument).execute_paper_plan(request)

    def cancel_paper_execution(self, instrument: str | RuntimeInstrument, receipt_id: str, *, timestamp, reason: str = "cancelled") -> PaperExecutionReceipt:
        self._require_running()
        return self.get_runtime(instrument).cancel_paper_execution(receipt_id, timestamp=timestamp, reason=reason)

    def reconcile_paper_execution(self, instrument: str | RuntimeInstrument, request: ExecutionReconciliationRequest) -> ExecutionReconciliationReport:
        self._require_running()
        runtime = self.get_runtime(instrument)
        return runtime.reconcile_paper_execution(request)

    def reconcile_paper_execution_receipt(self, instrument: str | RuntimeInstrument, receipt_id: str, *, timestamp) -> ExecutionReconciliationReport:
        self._require_running()
        return self.get_runtime(instrument).reconcile_paper_execution_receipt(receipt_id, timestamp=timestamp)

    def start_shadow_session(self, instrument: str | RuntimeInstrument, request: ShadowTradingSessionRequest):
        self._require_running()
        runtime = self.get_runtime(instrument)
        if request.instrument != runtime.instrument.value:
            raise ValueError("Shadow session request instrument does not match runtime.")
        return runtime.start_shadow_session(request)

    def observe_shadow_event(self, instrument: str | RuntimeInstrument, event_name: str, payload, *, timestamp):
        self._require_running()
        return self.get_runtime(instrument).observe_shadow_event(event_name, payload, timestamp=timestamp)

    def stop_shadow_session(self, instrument: str | RuntimeInstrument, *, timestamp, reason: str = "session_completed"):
        self._require_running()
        return self.get_runtime(instrument).stop_shadow_session(timestamp=timestamp, reason=reason)

    def get_shadow_snapshot(self, instrument: str | RuntimeInstrument):
        return self.get_runtime(instrument).get_shadow_snapshot()

    def get_shadow_summary(self, instrument: str | RuntimeInstrument, session_id: str):
        return self.get_runtime(instrument).get_shadow_summary(session_id)

    def configure_zerodha_credentials(self, credentials: ZerodhaCredentials):
        return self.zerodha_adapter.configure_credentials(credentials)

    def load_zerodha_instrument_tokens(self):
        return self.zerodha_adapter.load_instrument_tokens()

    def connect_zerodha_market_data(self):
        return self.zerodha_adapter.connect()

    def subscribe_zerodha_instruments(self, instruments: tuple[str, ...]):
        return self.zerodha_adapter.subscribe(instruments)

    def disconnect_zerodha_market_data(self):
        return self.zerodha_adapter.disconnect()

    def get_zerodha_connection_snapshot(self):
        return self.zerodha_adapter.snapshot()

    def reset_zerodha_adapter(self):
        return self.zerodha_adapter.reset()

    def start_live_shadow_coordinator(self):
        return self.live_shadow_session_coordinator.start()

    def start_live_shadow_session(self, request: LiveShadowSessionRequest):
        return self.live_shadow_session_coordinator.start_session(request)

    def observe_live_shadow_zerodha_state(self):
        return self.live_shadow_session_coordinator.observe_zerodha_state()

    def stop_live_shadow_session(self, *, timestamp, reason: str = "session_completed"):
        return self.live_shadow_session_coordinator.stop_session(timestamp=timestamp, reason=reason)

    def get_live_shadow_snapshot(self):
        return self.live_shadow_session_coordinator.snapshot()

    def get_live_shadow_report(self, session_id: str):
        return self.live_shadow_session_coordinator.get_report(session_id)

    def reset_live_shadow_coordinator(self):
        return self.live_shadow_session_coordinator.reset()

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
        self.performance_analytics_engine.reset(clear_persistent_data=False)
        self.live_validation_engine.reset(clear_persistent_data=False)
        self.historical_replay_engine.reset(clear_persistent_data=False)
        self.deterministic_backtest_engine.reset()
        self.zerodha_adapter.reset()
        self.live_shadow_session_coordinator.reset()
        for runtime in self._runtimes.values():
            runtime.reset()
            if previous_status is RuntimeStatus.RUNNING:
                runtime.start()
            elif previous_status is RuntimeStatus.STOPPED:
                runtime.stop()
        self._status = previous_status
        return self.snapshot()

    def reset_backtest_run_state(self) -> OrchestratorSnapshot:
        previous_status = self._status
        self.market_data_engine.clear()
        self.trade_journal_engine.reset()
        self.performance_analytics_engine.reset(clear_persistent_data=False)
        self.live_validation_engine.reset(clear_persistent_data=False)
        self.historical_replay_engine.reset(clear_persistent_data=False)
        for runtime in self._runtimes.values():
            runtime.reset()
            if previous_status is RuntimeStatus.RUNNING:
                runtime.start()
            elif previous_status is RuntimeStatus.STOPPED:
                runtime.stop()
        self._status = previous_status
        return self.snapshot()

    def prepare_backtest(self):
        return self._run_backtest_command("prepare")

    def start_backtest(self):
        return self._run_backtest_command("start")

    def pause_backtest(self):
        return self._run_backtest_command("pause")

    def resume_backtest(self):
        return self._run_backtest_command("resume")

    def stop_backtest(self):
        return self._run_backtest_command("stop")

    def reset_backtest(self):
        return self._run_backtest_command("reset")

    def _run_backtest_command(self, command_name: str):
        command = getattr(self.deterministic_backtest_engine, command_name)
        try:
            return command()
        except Exception as exc:
            return self.deterministic_backtest_engine.record_command_error(_safe_error(exc))

    def snapshot(self) -> OrchestratorSnapshot:
        return OrchestratorSnapshot(
            status=self._status,
            safety_mode=self._configuration.safety_mode,
            broker_mode=self.broker_adapter.mode,
            configured_instruments=self._configuration.instruments,
            shared_market_data_ready=self.market_data_engine.is_ready(),
            shared_trade_journal_ready=self.trade_journal_engine.is_ready(),
            runtime_snapshots=tuple(
                runtime.snapshot(
                    self._latest_journal_record_for(runtime.instrument),
                    performance_analytics=self.performance_analytics_engine.snapshot(instrument=runtime.instrument.value),
                )
                for runtime in self._runtimes.values()
            ),
            performance_analytics=self.performance_analytics_engine.snapshot(),
            live_validation=self.live_validation_engine.snapshot(),
            historical_replay=self.historical_replay_engine.snapshot(),
            deterministic_backtest=self.deterministic_backtest_engine.snapshot(),
            zerodha_connection=self.zerodha_adapter.snapshot(),
            live_shadow_session=self.live_shadow_session_coordinator.snapshot(),
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


def _safe_error(exc) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    for token in ("api_key", "api_secret", "access_token", "request_token"):
        text = text.replace(token, "[REDACTED]")
    return text[:500]
