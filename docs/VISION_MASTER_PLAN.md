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

## TradingView Evidence Assembly Coordinator V1

The TradingView Evidence Assembly Coordinator is an application-layer
coordinator, not a calculation engine. It is owned by `SymbolRuntime` and
collects the canonical outputs already produced by Candle, Price Action,
Camarilla, CPR, VWAP, Option Chain, and Market Context.

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
- Never calculate CPR, Camarilla, VWAP, Price Action, Option Chain, or Market
  Context inside the coordinator.

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
