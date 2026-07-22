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
