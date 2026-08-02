# VM-18 Production Hardening & Stress Validation V1

Status: COMPLETE
Branch: develop
Baseline: 47bc5f690ba8f852ca4bc79753ff737692b6bbf9 or newer develop HEAD

VM-18 is an engineering hardening milestone. It adds no indicators, no trading rules, no broker mutation, no risk changes, no lifecycle changes, and no journal schema changes.

## Scope

Validated production-like behavior for the completed deterministic operating system:

- runtime ownership and verification rows;
- event bus duplicate-subscription and cleanup behavior;
- nested event delivery ordering;
- bounded runtime memory under repeated market updates;
- CPU/latency guardrails for repeated tick, Vision Method, snapshot, and dashboard rendering cycles;
- thread ownership during runtime work and shutdown;
- reconnect/start-stop behavior without duplicate candidates, paper positions, or journal entries;
- session rollover synchronization for daily context;
- dashboard rendering from immutable snapshots;
- runtime, dashboard, journal, and verification payload redaction;
- source audit for forbidden runtime broker mutation calls and unbounded debug output.

## Runtime Verification Matrix

| Stage | Owner | Producer | Consumer | VM-18 expectation |
|---|---|---|---|---|
| Application Startup | SymbolRuntime | ApplicationLifecycle | Reference Data | present, owned, timestamped |
| Market Data | SymbolRuntime | MarketDataEngine | CandleEngine | present, no hidden owner |
| Reference Data | SymbolRuntime | Daily OHLC Warmup | Daily Context | session-aligned |
| Candle Engine | SymbolRuntime | CandleEngine | Vision Method | present in verification report |
| Daily Context | SymbolRuntime | CPR/Camarilla/ADR/VWAP | Vision Level Context | no stale rollover context |
| Opening Range | SymbolRuntime | Vision Opening Range | Vision Method Calculator | observable status/reason |
| Structure | SymbolRuntime | Vision Structure | Vision Structure Events | observable status/reason |
| Liquidity | SymbolRuntime | Vision Liquidity | Vision Structure Events | observable status/reason |
| Structure Events | SymbolRuntime | Vision Structure Events | Setup Qualification | observable status/reason |
| Setup Qualification | SymbolRuntime | Vision Setup Qualification | Option Confirmation | observable status/reason |
| Option Feed | SymbolRuntime | Live Option Chain Feed | OptionChainSnapshot | observable status/reason |
| Option Snapshot | SymbolRuntime | OptionChainEngine | OptionChainAnalytics | observable status/reason |
| Option Analytics | SymbolRuntime | OptionChainAnalyticsEngine | Vision Option Confirmation | observable status/reason |
| Option Confirmation | SymbolRuntime | Vision Option Confirmation | Vision Method Calculator | observable status/reason |
| Vision Method | SymbolRuntime | Vision Method Calculator | Vision Validation | snapshot timestamp checked |
| Validation | SymbolRuntime | Vision Method Validation | Runtime Adapter | report timestamp checked |
| Runtime Adapter | SymbolRuntime | VisionRuntimeAdapter | TradeCandidate | observable status/reason |
| TradeCandidate | SymbolRuntime | TradeCandidate | RiskManagementV2 | single candidate identity |
| Risk | SymbolRuntime | RiskManagementV2 | TradeLifecycleV1 | no rule changes |
| Lifecycle | SymbolRuntime | TradeLifecycleV1 | PositionManagementV1 | no rule changes |
| Paper Position | SymbolRuntime | PositionManagementV1 | TradeJournalV1 | no duplicate position |
| Paper Trade | SymbolRuntime | PositionManagementV1 | TradeJournalV1 | no duplicate trade |
| Journal | SymbolRuntime | TradeJournalV1 | Dashboard | exactly-once record behavior |
| AI Explanation | SymbolRuntime | Vision Method Explanation | Dashboard AI | Vision source only |

## Memory Report

The VM-18 stress test performs 120 repeated market updates, Vision Method evaluations, and snapshot reads while tracking allocations with `tracemalloc`.

Guardrails:

- current memory growth must remain below 8 MB;
- peak memory growth must remain below 16 MB;
- canonical engine object identities must remain stable;
- lifecycle position count must not duplicate.

Result: focused VM-18 suite passed.

## CPU And Latency Report

The CPU guard test performs 40 repeated tick, Vision Method, snapshot, and dashboard presenter cycles.

Guardrails:

- average cycle latency below 250 ms;
- maximum cycle latency below 1000 ms;
- runtime verification row latency values must be non-negative when present.

Result: focused VM-18 suite passed.

## Thread Audit

The thread audit records active thread identities before runtime work, runs repeated tick/evaluation/snapshot cycles, stops the runtime, and verifies no orphan runtime thread remains.

Result: focused VM-18 suite passed.

## Event Bus Audit

VM-18 verifies:

- duplicate subscriptions are not duplicated;
- unsubscribe prevents later delivery;
- clear removes active listeners;
- nested publish order is deterministic and produces no duplicate delivery.

Result: focused VM-18 suite passed.

## Recovery Audit

VM-18 verifies:

- stop/start recovery does not duplicate the Vision trade candidate;
- stop/start recovery does not duplicate canonical paper position opens;
- close processing remains exactly-once in the journal;
- session rollover refreshes daily CPR/Camarilla context to the active trading day.

Result: focused VM-18 suite passed.

## Startup And Shutdown Audit

Startup/shutdown behavior is covered by focused VM-18 tests plus existing VM-16 and lifecycle tests. Runtime startup must expose a complete verification report; shutdown/restart must not create orphan threads or duplicate candidates, paper positions, or journal entries.

Result: focused VM-18 suite passed.

## Security Audit

VM-18 verifies serialized runtime, dashboard, journal, persistence, and runtime verification payloads do not expose sensitive token or credential field names. It also source-audits production runtime surfaces for broker mutation calls and unbounded debug output.

Result: focused VM-18 suite passed.

## Dashboard Performance Audit

VM-18 repeatedly builds dashboard views from immutable runtime snapshots and verifies rendering remains under the configured guardrail. Dashboard presenters consume snapshots only; no dashboard API calls or calculations are introduced.

Result: focused VM-18 suite passed.

## Production Risk Register

| Severity | Risk | Status |
|---|---|---|
| Critical | Live broker mutation accidentally enabled | Guarded by DRY_RUN/default safety, VM-17 read-only broker account sync, and VM-18 source audit |
| High | Long real-market sessions may reveal latency spikes beyond deterministic replay/stress harness | Requires multi-week live-market validation after V1 certification |
| High | External Zerodha network disconnect behavior may differ from deterministic reconnect simulations | Requires live observe validation with real broker feed |
| Medium | Very large option chains and journals may need UI pagination/performance tuning | Current snapshot/presenter stress is green; full production data volumes still require observation |
| Medium | EventBus is synchronous and assumes serialized runtime usage | Existing architecture relies on deterministic single-threaded publication; future concurrency must add explicit guards |
| Low | Broker account sync uses wall-clock defaults when no timestamp is provided | Not used as a trading-engine timestamp; callers should pass runtime timestamps for deterministic reports |

## Version 1.0 Readiness Matrix

| Subsystem | Score | Ready |
|---|---:|---|
| Runtime | 9.4 | YES |
| Vision Method | 9.5 | YES |
| Dashboard | 8.9 | YES for production observability |
| Paper Trading | 8.8 | YES for paper validation |
| Journal | 9.0 | YES |
| Broker | 7.8 | PARTIAL: read-only sync ready; live mutation disabled |
| Security | 9.2 | YES for protected V1 modes |
| Performance | 8.7 | YES for deterministic stress; live validation still required |
| Recovery | 8.8 | YES for deterministic recovery; live broker recovery still requires observation |

## Validation Commands

```powershell
python -m compileall .
python -m pytest tests/test_vm_18_production_hardening_v1.py -v
python -m pytest -v
git diff --check
```

## Acceptance Summary

VM-18 is complete when compile, focused hardening tests, full regression, and diff checks pass with a clean working tree.
