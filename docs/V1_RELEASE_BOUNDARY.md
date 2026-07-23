# Vision Trading OS V1 Release Boundary

This document classifies the active Version 1 architecture and the retained
legacy boundaries. It is a repository hygiene document only; it does not define
new trading behavior.

## Canonical Active Runtime Chain

New production code must follow this active chain:

```text
Evidence Engines
-> Multi-Timeframe Evidence Fusion
-> Market State
-> Expert Setup Classification
-> Chart Explanation
-> AI Reasoning V2
-> StrategyDecisionV2
-> RiskManagementV2
-> TradeLifecycleV1
-> TradeJournalV1
```

AI Reasoning V2 consumes deterministic intelligence snapshots only:

- `MultiTimeframeEvidenceSnapshot`
- `MarketStateSnapshot`
- `ExpertSetupClassificationSnapshot`
- `ChartExplanationSnapshot`

New code must not depend on `MarketContextV2` unless the change is explicitly
approved as compatibility maintenance.

## Package Classification

| Package | Classification | Boundary |
|---|---|---|
| `core/` | ACTIVE | Event bus, shared events, enums, and canonical models. |
| `application/` | ACTIVE | Runtime orchestration, desktop integration, replay/backtest drivers, and V1 runtime coordinators. |
| `engines/` | ACTIVE | Canonical evidence, intelligence, decision, risk, lifecycle, journal, replay, backtest, analytics, and safety engines. |
| `engines/market_context_v2/` | LEGACY-TESTED | Retained with tests as historical/compatibility code. It is not part of the active AI V2 chain. |
| `dashboard/` | ACTIVE | Functional desktop dashboard and read-only panels. Dashboard remains partial as a product surface. |
| `brokers/` | ACTIVE | Canonical broker abstractions, Zerodha auth, historical, instruments, market data, option contracts, option subscriptions, and dry-run broker adapter. |
| `adapters/` | ACTIVE | Zerodha read-only live adapter used for live market-data observation. |
| `config/` | ACTIVE | Local configuration helpers. |
| `database/` | UNKNOWN | No canonical active runtime dependency was verified in this cleanup milestone. Retain until a dedicated audit. |
| `engine/` | COMPATIBILITY | Older prototype modules retained because dashboard controller imports older engine names. Do not extend for new V1 runtime work. |
| `models/` | COMPATIBILITY | Older UI/prototype models retained for compatibility. Do not use for new deterministic runtime snapshots. |
| `market/` | COMPATIBILITY | Older market enums/models retained where compatibility imports still exist. New runtime code should prefer `core/`. |
| `services/` | COMPATIBILITY | Older service facades retained for UI/service compatibility. Do not use for deterministic engine logic. |
| `broker/` | COMPATIBILITY | Older broker/session helpers retained for compatibility. New broker work should use `brokers/`. |

## V1 Status Boundaries

| Area | Status | Notes |
|---|---|---|
| Price Action V1 | COMPLETE | Canonical V1 engine exists and is tested. Institutional Price Action V2 is future work. |
| Option Chain V1 | COMPLETE | Canonical V1 and analytics/integration packages exist and are tested. Institutional Option Chain V2 is future work. |
| Paper Trading V1 | COMPLETE | Paper execution, analytics, replay, and backtest integration exist. |
| Zerodha live market data | COMPLETE | Read-only live market data is implemented and tested. |
| Zerodha live option chain | COMPLETE / DISABLED BY DEFAULT | Live option-chain runtime exists but must be explicitly enabled. |
| Live broker order placement | DISABLED BY DESIGN | Broker adapter supports dry-run and guarded client calls; application startup requires protected modes by default. |
| Broker holdings/position/margin synchronization | PARTIAL / FUTURE | No complete production synchronization layer is part of V1. |
| Dashboard | PARTIAL | Functional read-only workstation panels exist; full product UX polish remains future work. |
| Voice | PARTIAL / LEGACY | Voice panel/service prototypes exist but are not a complete production voice assistant. |

## Prohibited Future Dependencies

- New active runtime code must not import from `engines.market_context_v2`.
- New deterministic runtime code must not import from prototype packages
  `engine/`, `models/`, `market/`, `services/`, or `broker/` unless the change
  is explicitly compatibility maintenance.
- Evidence engines must not call broker APIs.
- Intelligence and explanation engines must not calculate indicators.
- AI Reasoning V2 must remain downstream of Chart Explanation.
