# Vision Trading OS

Version: 1.0.0

Vision Trading OS is a synchronous, deterministic trading-analysis workstation. The current release candidate runs in protected modes only and is designed for analysis, validation, and dashboard review.

## Architecture

The application composes one `EventBus`, one `ApplicationOrchestrator`, and one `ApplicationLifecycleManager` through `ApplicationBootstrap`. Runtime state flows from engines into immutable `RuntimeSnapshot` values and then through dashboard presenters before widgets render read-only views.

## Candle Boundary Policy

Intraday runtime candles are session-anchored. For the supported Indian index runtime, the canonical intraday anchor is `09:15` local exchange time, so `1m`, `3m`, `5m`, `15m`, and `30m` candles derive their boundaries from the session open instead of midnight. Daily candles follow trading-day boundaries and remain outside the intraday multi-timeframe runtime. Downstream engines such as Price Action, Market Context, and TradingView Evidence consume these canonical closed candles and must not implement separate aggregation rules.

## ADR Evidence

ADR Engine V1 calculates Average Daily Range from externally supplied daily OHLC history and the current session high/low maintained by the runtime. ADR is an evidence source only: it publishes immutable range context, is owned once per instrument runtime, and is consumed by TradingView Evidence Assembly without recalculating ADR inside the evidence mapper.

## Moving Average Evidence

Moving Average Context Engine V1 calculates EMA-only context from closed candles already owned by the runtime. The default profile is EMA 20, EMA 50, and EMA 200, with profile periods centralized in `RuntimeConfiguration` for future extension. One MA context engine is owned per instrument/timeframe lane, so `1m`, `3m`, `5m`, `15m`, and `30m` evidence remains isolated. TradingView Evidence Assembly consumes the immutable MA context snapshot and never calculates moving averages inside the evidence mapper.

## Momentum Evidence

Momentum Context Engine V1 calculates generic period-based momentum from closed candles already owned by the runtime. The default period is 14 and is centralized in `RuntimeConfiguration` for future extension. One Momentum context engine is owned per instrument/timeframe lane, so each runtime lane remains isolated. TradingView Evidence Assembly consumes the immutable Momentum context snapshot and never calculates momentum inside the evidence mapper.

## Volume Evidence

Volume Context Engine V1 calculates average volume and relative volume from closed candles already owned by the runtime. The default lookback is 20 periods and is centralized in `RuntimeConfiguration` for future extension. One Volume context engine is owned per instrument/timeframe lane, so each runtime lane remains isolated. TradingView Evidence Assembly consumes the immutable Volume context snapshot and never calculates volume context inside the evidence mapper.

## Multi-Timeframe Evidence Fusion

Multi-Timeframe Evidence Fusion Engine V1 is the first deterministic intelligence layer. It is owned once per instrument runtime and consumes only immutable TradingView Evidence snapshots from configured timeframe lanes. It compares existing evidence agreement, conflict, dominance, and completeness, then publishes immutable fusion context without calculating indicators or producing trade decisions.

## Market State

Market State Engine V1 consumes only the immutable Multi-Timeframe Evidence Fusion snapshot for one instrument. It describes the current market environment, such as trending, ranging, transitioning, expanding, compressing, volatile, quiet, or balanced. It publishes structural context and evidence quality through the EventBus without calculating indicators, inferring trade intent, or calling strategy, risk, confidence, execution, or broker layers.

## Expert Setup Classification

Expert Setup Classification Engine V1 consumes only Multi-Timeframe Evidence Fusion and Market State snapshots. It classifies observable setups such as trend continuation, pullback continuation, breakout, failed breakout, range day, trend day, compression, expansion, traps, reversal attempts, liquidity sweeps, or no-quality setup. It remains descriptive only and never produces trade direction, entries, exits, risk, confidence scoring, execution requests, or broker calls.

## Chart Explanation

Chart Explanation Engine V1 consumes only Multi-Timeframe Evidence Fusion, Market State, and Expert Setup Classification snapshots. It converts deterministic intelligence into stable human-readable explanations: headline, market summary, setup explanation, supporting evidence, conflicting evidence, and caution notes. It uses fixed wording templates, publishes through the EventBus, and never calculates indicators, creates signals, or recommends orders.

## Execution Modes

- Safety mode: `ANALYSIS_ONLY` by default.
- Broker execution mode: `DRY_RUN`.
- Live order submission is not enabled by default.

## Supported Instruments

NIFTY, BANKNIFTY, SENSEX

## Startup

Desktop dashboard:

```powershell
python desktop_main.py
```

The startup path validates configuration, supported instruments, execution mode, safety mode, and core runtime dependencies before composing the application.

Offline desktop mode:

```powershell
$env:LIVE_MARKET_DATA_ENABLED="false"
python desktop_main.py
```

Live market-data desktop mode uses Zerodha Kite Connect credentials from environment variables. Obtain the API key and API secret from the Zerodha developer console, and provide a current access token for the session. Zerodha access tokens normally expire and may need renewal. Keep credentials in local environment variables only; never commit `.env` files or real secrets.

Required live market-data variables are shown in `.env.example`:

```powershell
$env:ZERODHA_API_KEY="<your api key>"
$env:ZERODHA_API_SECRET="<your api secret>"
$env:ZERODHA_ACCESS_TOKEN="<current access token>"
$env:NIFTY_INSTRUMENT_TOKEN="<token>"
$env:BANKNIFTY_INSTRUMENT_TOKEN="<token>"
$env:SENSEX_INSTRUMENT_TOKEN="<token>"
$env:LIVE_MARKET_DATA_ENABLED="true"
$env:LIVE_MARKET_DATA_AUTO_CONNECT="true"
python desktop_main.py
```

Live market data enables WebSocket ticks for NIFTY, BANKNIFTY, and SENSEX only. Order execution remains protected: broker mode is `DRY_RUN`, safety mode remains `ANALYSIS_ONLY`, and live order placement is not enabled.

Live option-chain integration is disabled by default. To enable the dashboard option-chain runtime, keep live market data enabled and add:

```powershell
$env:LIVE_OPTION_CHAIN_ENABLED="true"
$env:LIVE_OPTION_CHAIN_AUTO_START="true"
$env:OPTION_CHAIN_STRIKES_EACH_SIDE="5"
python desktop_main.py
```

Option contracts are discovered dynamically from Zerodha's instrument master after the first valid spot tick for NIFTY, BANKNIFTY, or SENSEX. Do not configure or store option tokens manually. If option-chain discovery or subscription fails, the spot feed continues and the Option Chain panel shows a sanitized runtime error. Zerodha access tokens are valid only for the current session/day and must not be committed.

## Performance Analytics

Performance Analytics V1 consumes completed `PaperTradeRecord` values only. It is read-only: `ANALYSIS_ONLY` and `DRY_RUN` remain preserved, no broker execution API is called, and `broker_order_calls` remains `0`.

The persistent journal defaults to `logs/performance_journal.jsonl` and can be configured with `PERFORMANCE_JOURNAL_PATH`. JSON Lines records include a schema version, preserve timezone-aware datetimes, and tolerate corrupt lines without deleting valid records. Exports are available as UTF-8 CSV and deterministic `.xlsx` workbooks under `PERFORMANCE_EXPORT_DIRECTORY`.

Definitions: wins are `net_pnl > 0`, losses are `net_pnl < 0`, and breakeven trades are `net_pnl == 0`. Profit factor is gross profit divided by absolute gross loss and is `None` when undefined, never infinity. Expectancy is average completed-trade net P&L. R metrics use stored `reward_risk_realized`. Equity curve orders trades by `exit_time, trade_id`; percentage drawdown uses configured `PERFORMANCE_STARTING_EQUITY`. Daily periods use `PaperTradeRecord.trading_date`, weekly periods use ISO weeks, and monthly periods use calendar months.

The deterministic post-trade review is generated from stored trade facts only. It does not call external AI services and does not infer unsupported psychological or market claims.

## Live Market Validation

Live Market Validation V1 is an optional observability layer for checking real-time market-data flow and downstream engine consistency. It is not a market-data engine, candle engine, option-chain engine, strategy engine, analytics engine, or broker execution feature.

Default state:

```text
LIVE_VALIDATION_ENABLED=false
LIVE_VALIDATION_MODE=OFF
```

Supported modes are `OFF`, `SIMULATION`, and `LIVE_OBSERVE`. Simulation mode consumes deterministic test or replayed events without broker connectivity. Live observe mode watches real incoming market data and existing engine outputs only after explicit configuration and user action. Neither mode can place, modify, cancel, or submit broker orders.

Supported validation instruments are NIFTY, BANKNIFTY, and SENSEX. Safety remains protected: `ANALYSIS_ONLY` and `DRY_RUN` are preserved, live order execution remains disabled, and `broker_order_calls` must remain `0`.

The validator observes existing `EventBus` events, `ApplicationOrchestrator` runtime snapshots, candle output, price-action output, option-chain output, CPR, Camarilla, VWAP, paper-trading events, and performance analytics events. It validates data quality, freshness, event flow, reconnect recovery, latency, bounded-memory behavior, and persistence health without recalculating trading decisions.

Reports are written under `logs/live_validation` by default. Findings use JSON Lines with explicit schema versions, and final session reports use deterministic JSON with atomic replacement. Secrets, access tokens, API keys, and raw broker payloads are excluded.

Health statuses are deterministic: active critical findings produce failed health, active errors produce unhealthy health, active warnings produce degraded health, observed clean components become healthy, and unobserved components remain unknown or not enabled. Final outcomes are `PASS`, `PASS_WITH_WARNINGS`, `FAIL`, or `INCOMPLETE`.

Focused validation tests:

```powershell
python -m pytest tests/test_live_market_validation_v1.py -v
```

## Historical Market Replay

Historical Market Replay V1 is an optional offline source for deterministic market-session playback. It publishes recorded tick and option-chain evidence through the existing `EventBus` so current engines and validation observers can be tested without a live broker feed.

Default state:

```text
HISTORICAL_REPLAY_ENABLED=false
HISTORICAL_REPLAY_MODE=OFF
```

Supported modes are `STEP`, `REALTIME`, and `ACCELERATED`. Replay sessions are JSON Lines files with a schema-versioned manifest followed by ordered tick or option-chain records for NIFTY, BANKNIFTY, and SENSEX. Replay refuses to start while live market data is active, never writes per replayed record, and stores only terminal reports under `logs/historical_replay`.

Replay startup is explicit. `HISTORICAL_REPLAY_AUTO_LOAD=true` requires an enabled replay mode and a source path. `HISTORICAL_REPLAY_AUTO_START=true` also requires auto-load and cannot be combined with live market-data auto-connect. Desktop startup wires replay safety to the actual live market-data runtime, so replay and live publication cannot run at the same time.

Safety remains protected: `ANALYSIS_ONLY` and `DRY_RUN` are required, live order execution remains disabled, and `broker_order_calls` must remain `0`.

Focused replay tests:

```powershell
python -m pytest tests/test_historical_market_replay_v1.py -v
```

## Deterministic Backtest

Historical Replay reproduces market events. Deterministic Backtest coordinates those events through the existing trading-analysis and paper-execution pipeline and evaluates the resulting performance.

Default state:

```text
BACKTEST_ENABLED=false
BACKTEST_MODE=SINGLE_SESSION
```

Supported V1 modes are `SINGLE_SESSION` and `BATCH`. Batch sessions run sequentially and never concurrently. The backtest orchestrator uses the approved Historical Market Replay Engine, the shared `EventBus`, existing application runtime engines, Paper Trading, and Performance Analytics. It does not implement another trading engine, candle calculator, strategy engine, risk engine, fill engine, analytics engine, ticker router, or EventBus.

Backtest configuration is disabled by default and does not inspect session files unless enabled and prepared. Session paths are ordered with `BACKTEST_SESSION_PATHS`, separated by semicolons on Windows. Reports are written under `BACKTEST_OUTPUT_DIRECTORY` and are terminal JSON reports only; no durable data is written per replay record, candle, signal, dashboard refresh, or cooperative poll.

Lifecycle states are `IDLE`, `READY`, `RUNNING`, `PAUSED`, `COMPLETED`, `STOPPED`, and `FAILED`. Desktop rendering remains cooperative: each refresh advances at most a bounded unit of running backtest work. `Prepare`, `Start`, `Pause`, `Resume`, `Stop`, and `Reset` commands call public backtest APIs only.

Deterministic run fingerprints are built from stable inputs: schema version, ordered replay session identities, replay manifest details, execution mode, and safe configuration. Runtime timestamps, process IDs, output paths, random values, and object memory addresses are excluded. When reproducibility checking is enabled, result digests compare stable terminal outcomes and bounded finding codes while excluding report paths and wall-clock metadata.

Backtesting is mutually exclusive with live market-data and live option-chain publication. A current live runtime in `STARTING`, `RUNNING`, or `STOPPING`, or a connecting/connected/reconnecting/disconnecting WebSocket, blocks backtest startup. Backtest activity also blocks live auto-connect. The system never forces a live disconnect, mutates live configuration, or switches from live to replay automatically.

Safety remains protected: `ANALYSIS_ONLY` and `DRY_RUN` are mandatory, live order execution remains disabled, and `broker_order_calls` must remain `0`. Open paper positions at terminal completion are reported explicitly. If no closed paper trades are produced, the result remains valid and records a clear `NO_TRADES` finding instead of inventing fills or placeholder performance.

Known V1 limitations: no live trading, no broker order placement, no strategy optimization, no parameter-grid search, no walk-forward testing, no Monte Carlo simulation, no multiprocessing, no threads, no asyncio, no distributed workers, and no portfolio allocation.

Focused backtest tests:

```powershell
python -m pytest tests/test_deterministic_backtest_v1.py -v
```

## Testing

Full regression suite:

```powershell
python -m pytest -v
```

Focused dashboard suite:

```powershell
python -m pytest tests/test_dashboard* -v
```

Focused price-action suite:

```powershell
python -m pytest tests/test_price_action* -v
```
