# Vision Trading OS - MASTER PLAN

## Project Goal

Build a production-quality event-driven trading platform for: - NIFTY -
BANKNIFTY - SENSEX

Primary decision flow: Price Action -\> Market Context -\> Option Chain
-\> Confirmation -\> AI Reasoning

## Development Rules

1.  Every modified file is provided as a COMPLETE file.
2.  Every milestone ends with working code, tests, and a Git commit.
3.  No placeholder code.
4.  Build Version 1 first, extend later.

## Folder Structure

core/ enums/ models/ base_engine.py event_bus.py events.py

engines/ market_data/ candle/ camarilla/ cpr/ vwap/ price_action/
market_context/ option_chain/ ai/

tests/ docs/

## Completed

-   Event Bus
-   Events
-   Base Engine
-   DailyOHLC
-   Candle
-   BuildingCandle
-   Tick
-   TimeFrame
-   Instrument
-   Exchange
-   Camarilla Engine
-   CPR Engine
-   TradingView Evidence Mapping Engine
-   TradingView Evidence Assembly Coordinator
-   ADR Engine
-   Moving Average Context Engine
-   Momentum Context Engine
-   Volume Context Engine
-   Multi-Timeframe Evidence Fusion Engine
-   Market State Engine
-   Expert Setup Classification Engine
-   Chart Explanation Engine

## TradingView Evidence Assembly Coordinator V1

The TradingView Evidence Assembly Coordinator is an application-layer
coordinator, not a calculation engine. It is owned by `SymbolRuntime` and
collects the canonical outputs already produced by Candle, Price Action,
Camarilla, CPR, VWAP, ADR, Moving Average Context, Momentum Context, Volume
Context, Option Chain, and Market Context.

Event flow:

Tick -> Market Data Engine -> Candle Engine -> existing analysis engines ->
TradingView Evidence Assembly Coordinator -> TradingView Evidence Mapping Engine
-> `TRADINGVIEW_EVIDENCE_MAPPED` or `TRADINGVIEW_EVIDENCE_PARTIAL`.

Snapshot lifecycle:

- Wait until a latest price and latest closed candle exist.
- Build one deterministic immutable TradingView evidence request from existing
  runtime state.
- Delegate mapping and EventBus publishing to the existing TradingView Evidence
  Mapping Engine.
- Publish partial evidence when required upstream analytical snapshots are
  missing, stale, or invalid.
- Never calculate CPR, Camarilla, VWAP, ADR, Moving Average Context, Momentum
  Context, Volume Context, Price Action, Option Chain, or Market Context inside
  the coordinator.

## Moving Average Context Engine V1

Moving Average Context is an evidence engine, not a strategy or risk engine. It
consumes closed candles for a single `Instrument` and `TimeFrame` lane and
publishes immutable EMA context through `MA_CONTEXT_UPDATED`,
`MA_CONTEXT_PARTIAL`, `MA_CONTEXT_INVALID`, `MA_CONTEXT_FAILED`, and
`MA_CONTEXT_STATE_UPDATED`.

Runtime ownership:

- One `MovingAverageContextEngine` per configured instrument/timeframe lane.
- No market-data ownership, tick processing, historical downloads, order
  execution, confidence scoring, or position sizing.
- EMA 20, EMA 50, and EMA 200 are the default profile; future profile periods
  are configured centrally without changing runtime ownership.

Event flow:

Tick -> Market Data Engine -> Candle Engine -> closed Candle -> Moving Average
Context Engine -> TradingView Evidence Assembly Coordinator -> TradingView
Evidence Mapping Engine.

## Momentum Context Engine V1

Momentum Context is an evidence engine, not a strategy, risk, confidence, or
position-sizing engine. It consumes closed candles for a single `Instrument` and
`TimeFrame` lane and publishes immutable momentum context through
`MOMENTUM_CONTEXT_UPDATED`, `MOMENTUM_CONTEXT_PARTIAL`,
`MOMENTUM_CONTEXT_INVALID`, `MOMENTUM_CONTEXT_FAILED`, and
`MOMENTUM_CONTEXT_STATE_UPDATED`.

Runtime ownership:

- One `MomentumContextEngine` per configured instrument/timeframe lane.
- No market-data ownership, tick processing, historical downloads, order
  execution, confidence scoring, or position sizing.
- The default period is 14; future period configuration is centralized without
  changing runtime ownership.

Event flow:

Tick -> Market Data Engine -> Candle Engine -> closed Candle -> Momentum
Context Engine -> TradingView Evidence Assembly Coordinator -> TradingView
Evidence Mapping Engine.

## Volume Context Engine V1

Volume Context is an evidence engine, not a strategy, risk, confidence,
execution, or position-sizing engine. It consumes closed candles for a single
`Instrument` and `TimeFrame` lane and publishes immutable volume context through
`VOLUME_CONTEXT_UPDATED`, `VOLUME_CONTEXT_PARTIAL`,
`VOLUME_CONTEXT_INVALID`, `VOLUME_CONTEXT_FAILED`, and
`VOLUME_CONTEXT_STATE_UPDATED`.

Runtime ownership:

- One `VolumeContextEngine` per configured instrument/timeframe lane.
- No market-data ownership, tick processing, historical downloads, order
  execution, confidence scoring, or position sizing.
- The default lookback is 20 periods; future lookback configuration is
  centralized without changing runtime ownership.
- Volume history is append-only. Gap candles are allowed, and same end-time
  correction is allowed only when it cannot rewrite finalized history.

Event flow:

Tick -> Market Data Engine -> Candle Engine -> closed Candle -> Volume Context
Engine -> TradingView Evidence Assembly Coordinator -> TradingView Evidence
Mapping Engine.

## Multi-Timeframe Evidence Fusion Engine V1

Multi-Timeframe Evidence Fusion is a deterministic intelligence engine, not an
indicator engine, strategy engine, confidence engine, or execution component. It
is owned once per `SymbolRuntime` instrument and consumes only immutable
`TradingViewEvidenceSnapshot` values already produced by the configured
timeframe lanes.

Runtime ownership:

- One `MultiTimeframeEvidenceFusionEngine` per instrument runtime.
- No market-data ownership, tick processing, historical downloads, indicator
  calculations, trade decisions, confidence scoring, risk evaluation, or order
  execution.
- Timeframe lanes remain independent through Candle, Price Action, Market
  Context, and TradingView Evidence. Fusion compares their completed evidence
  snapshots and produces one immutable multi-timeframe understanding snapshot.

Event flow:

Tick -> Market Data Engine -> Candle Engine -> closed Candle -> per-timeframe
analysis engines -> TradingView Evidence Assembly Coordinator -> TradingView
Evidence Mapping Engine -> Multi-Timeframe Evidence Fusion Engine.

Fusion lifecycle:

- Publish `MULTI_TIMEFRAME_EVIDENCE_UPDATED` when all configured lanes have
  complete evidence and observable agreement/conflict context changes.
- Publish `MULTI_TIMEFRAME_EVIDENCE_PARTIAL` when a timeframe or evidence source
  is missing, stale, or invalid.
- Publish `MULTI_TIMEFRAME_EVIDENCE_INVALID` for malformed fusion input and
  `MULTI_TIMEFRAME_EVIDENCE_FAILED` only for unexpected engine failures.
- Suppress duplicate publication when the observable fusion snapshot is
  unchanged.

## Market State Engine V1

Market State is a deterministic intelligence engine, not an evidence engine,
strategy engine, risk engine, confidence engine, or execution component. It is
owned once per `SymbolRuntime` instrument and consumes only the latest immutable
`MultiTimeframeEvidenceSnapshot`.

Runtime ownership:

- One `MarketStateEngine` per instrument runtime.
- No market-data ownership, tick processing, historical downloads, indicator
  calculations, trade decisions, confidence scoring, risk evaluation, or order
  execution.
- Price Action, CPR, Camarilla, VWAP, ADR, Moving Average Context, Momentum
  Context, Volume Context, Option Chain, and Market Context remain upstream
  evidence responsibilities and are never consumed directly by Market State.

Event flow:

Tick -> Market Data Engine -> Candle Engine -> closed Candle -> per-timeframe
analysis engines -> TradingView Evidence Assembly Coordinator -> TradingView
Evidence Mapping Engine -> Multi-Timeframe Evidence Fusion Engine -> Market
State Engine.

Market State lifecycle:

- Publish `MARKET_STATE_UPDATED` when a complete fusion snapshot produces a new
  observable market environment.
- Publish `MARKET_STATE_PARTIAL` when fusion is missing, stale, or partial.
- Publish `MARKET_STATE_INVALID` for malformed Market State input and
  `MARKET_STATE_FAILED` only for unexpected engine failures.
- Suppress duplicate publication when the observable Market State snapshot is
  unchanged.

## Expert Setup Classification Engine V1

Expert Setup Classification is a deterministic intelligence engine, not a
strategy engine, risk engine, confidence engine, or execution component. It is
owned once per `SymbolRuntime` instrument and consumes only the latest immutable
`MultiTimeframeEvidenceSnapshot` and `MarketStateSnapshot`.

Runtime ownership:

- One `ExpertSetupClassificationEngine` per instrument runtime.
- No market-data ownership, tick processing, historical downloads, indicator
  calculations, trade decisions, confidence scoring, risk evaluation, or order
  execution.
- Price Action, CPR, Camarilla, VWAP, ADR, Moving Average Context, Momentum
  Context, Volume Context, Option Chain, and Market Context remain upstream
  responsibilities and are never consumed directly by Setup Classification.

Event flow:

Tick -> Market Data Engine -> Candle Engine -> closed Candle -> per-timeframe
analysis engines -> TradingView Evidence Assembly Coordinator -> TradingView
Evidence Mapping Engine -> Multi-Timeframe Evidence Fusion Engine -> Market
State Engine -> Expert Setup Classification Engine.

Setup Classification lifecycle:

- Publish `SETUP_CLASSIFICATION_UPDATED` when complete Fusion and Market State
  inputs produce a new observable setup classification.
- Publish `SETUP_CLASSIFICATION_PARTIAL` when Fusion or Market State is missing,
  stale, or partial.
- Publish `SETUP_CLASSIFICATION_INVALID` for malformed setup input and
  `SETUP_CLASSIFICATION_FAILED` only for unexpected engine failures.
- Suppress duplicate publication when the observable setup classification
  snapshot is unchanged.

## Chart Explanation Engine V1

Chart Explanation is a deterministic explanation engine, not an AI engine,
strategy engine, signal generator, risk engine, or execution component. It is
owned once per `SymbolRuntime` instrument and consumes only immutable
`MultiTimeframeEvidenceSnapshot`, `MarketStateSnapshot`, and
`ExpertSetupClassificationSnapshot` values.

Runtime ownership:

- One `ChartExplanationEngine` per instrument runtime.
- No market-data ownership, tick processing, historical downloads, indicator
  calculations, trade decisions, confidence scoring, risk evaluation, or order
  execution.
- Chart Explanation translates deterministic intelligence into fixed,
  reproducible text for downstream AI consumers. It never invents market
  understanding and never consumes raw evidence engines directly.

Event flow:

Tick -> Market Data Engine -> Candle Engine -> closed Candle -> per-timeframe
analysis engines -> TradingView Evidence Assembly Coordinator -> TradingView
Evidence Mapping Engine -> Multi-Timeframe Evidence Fusion Engine -> Market
State Engine -> Expert Setup Classification Engine -> Chart Explanation Engine.

Chart Explanation lifecycle:

- Publish `CHART_EXPLANATION_UPDATED` when complete intelligence inputs produce
  a new observable explanation.
- Publish `CHART_EXPLANATION_PARTIAL` when Fusion, Market State, or Expert
  Setup Classification is missing, stale, or partial.
- Publish `CHART_EXPLANATION_INVALID` for malformed explanation input and
  `CHART_EXPLANATION_FAILED` only for unexpected engine failures.
- Suppress duplicate publication when the observable explanation snapshot is
  unchanged.

## AI Reasoning V2 Model Contract

AI Reasoning V2 is the downstream consumer of deterministic market
intelligence. Its model contract is no longer based on `MarketContextV2Snapshot`
and does not consume raw indicator engines.

Model inputs:

- `MultiTimeframeEvidenceSnapshot`
- `MarketStateSnapshot`
- `ExpertSetupClassificationSnapshot`
- `ChartExplanationSnapshot`
- optional previous `AIReasoningV2Snapshot`

Model contract:

- All upstream snapshots must be immutable deterministic intelligence snapshots.
- All upstream snapshots must share the same instrument, trading date, and
  timezone-aware timestamp.
- AI Reasoning V2 snapshots store deterministic upstream intelligence references
  and source fingerprints instead of legacy Market Context V2 state.
- AI Reasoning V2 confidence is not inherited directly from Market Context V2.
- Runtime, engine, interpreter, composer, strategy, lifecycle, risk, and journal
  migration are intentionally deferred to later AI Reasoning V2 migration
  stages.

## Current Milestone

Milestone 7: Candle Engine V1

Goals: - Receive Tick - Build 1-minute candle - Publish CANDLE_OPENED -
Publish CANDLE_UPDATED - Publish CANDLE_CLOSED - Unit Test - Git Commit

## Next Milestones

1.  Candle Engine
2.  VWAP Engine
3.  Price Action Engine
4.  Market Context Engine
5.  Option Chain Engine
6.  AI Reasoning Engine
7.  Risk Manager
8.  Execution Manager
9.  Dashboard
10. Live Trading
