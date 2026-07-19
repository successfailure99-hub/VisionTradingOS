from datetime import timedelta

from application import ApplicationBootstrap, RuntimeConfiguration, RuntimeInstrument
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.models.tick import Tick
from dashboard.presenters import build_journal_view, build_position_view
from engines.paper_trading import PaperExitType, PaperTradingConfiguration

from tests.test_risk_trade_plan_engine import NOW, ai, cam, config, context, cpr, option_chain, price_action


def tick(price, seconds):
    return Tick(Instrument.NIFTY, Exchange.NSE, NOW + timedelta(seconds=seconds), price, 1, price - 0.5, price + 0.5, 0)


def composed_runtime():
    lifecycle = ApplicationBootstrap(
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.SENSEX),
            risk_configuration=config(),
            paper_trading_configuration=PaperTradingConfiguration(),
        )
    ).create_application()
    lifecycle.start()
    runtime = lifecycle.orchestrator.get_runtime("NIFTY")
    runtime.price_action_engine._data = price_action()
    runtime.option_chain_engine._state = option_chain()
    runtime.camarilla_engine._levels = cam()
    runtime.cpr_engine._levels = cpr()
    runtime.ai_reasoning_engine._state = ai()
    runtime.market_context_engine._state = context()
    return lifecycle, runtime


def test_approved_bullish_trade_plan_completes_target_lifecycle_through_runtime():
    lifecycle, runtime = composed_runtime()
    runtime.run_strategy(context(), ai())
    pending = runtime.snapshot().paper_trading.order
    assert pending is not None
    assert pending.entry_price == 100.0

    runtime.process_tick(tick(103.0, 1))
    runtime.process_tick(tick(100.0, 2))
    assert runtime.snapshot().paper_trading.position is not None

    runtime.process_tick(tick(106.0, 3))
    runtime.process_tick(tick(110.0, 4))
    snapshot = runtime.snapshot()
    assert snapshot.paper_trading.position is None
    assert snapshot.paper_trading.latest_record.exit_type is PaperExitType.TARGET
    assert snapshot.paper_trading.latest_record.net_pnl == 900.0
    assert runtime.trade_plan_engine.daily_state.trades_completed == 1
    assert runtime.trade_plan_engine.daily_state.realized_pnl == 900.0
    assert runtime.order_engine.latest_order is None
    assert snapshot.paper_trading.diagnostics.broker_order_calls == 0
    assert build_position_view(snapshot).status == "No Active Position"
    assert build_journal_view(snapshot).records == 1
    lifecycle.stop()


def test_instrument_isolation_keeps_nifty_paper_position_out_of_other_tabs():
    lifecycle, runtime = composed_runtime()
    runtime.run_strategy(context(), ai())
    runtime.process_tick(tick(103.0, 1))
    runtime.process_tick(tick(100.0, 2))
    banknifty = lifecycle.orchestrator.get_runtime("BANKNIFTY").snapshot()
    sensex = lifecycle.orchestrator.get_runtime("SENSEX").snapshot()
    assert banknifty.paper_trading.order is None
    assert banknifty.paper_trading.position is None
    assert sensex.paper_trading.order is None
    assert sensex.paper_trading.position is None
    lifecycle.stop()
