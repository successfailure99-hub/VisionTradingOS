# Changelog

## V1 Release Hardening

- Removed tracked generated Python cache artifacts, a generated repository tree,
  a stale patch artifact, and the tracked local `.env` file from version
  control.
- Added explicit V1 package-boundary documentation in
  `docs/V1_RELEASE_BOUNDARY.md`.
- Added architecture guards to prevent tracked generated artifacts and active
  AI V2 runtime dependencies on the retained MarketContextV2 package.
- Clarified that retained legacy-looking packages are compatibility or
  legacy-tested boundaries unless a future dedicated audit proves safe removal.

## RC1 Certification - AI Reasoning V2 Migration

- Certified the deterministic AI Reasoning V2 runtime chain from evidence fusion through trade journaling.
- Removed remaining runtime imports of `SUPPORTED_INSTRUMENTS` from the legacy MarketContextV2 package.
- Documented the RC1 dependency graph, legacy-reference audit, dead-code status, architecture validation, performance notes, and regression requirements.
- Confirmed the active AI V2 chain no longer consumes MarketContextV2, raw indicators, raw candles, or evidence-engine internals.

## VM-17 Broker Readiness & Read-Only Account Synchronization

- Added account-wide read-only broker synchronization owned by `ApplicationOrchestrator`.
- Added immutable broker account, position, holding, order-status, reconciliation, and runtime-verification models.
- Added deterministic auth/session, stale-preservation, retry-suppression, reconnection, and mutation-disabled states.
- Added dashboard runtime visibility for broker authentication, connection, margins, positions, holdings, orders, snapshot age, blocking reason, and mutation mode.
- Added architecture tests proving the VM-17 path preserves read-only broker safety, avoids per-symbol account duplication, redacts sensitive material, suppresses duplicate refreshes, preserves stale snapshots after transient failures, and never exposes broker mutation through the dashboard/runtime path.

## VM-18 Production Hardening & Stress Validation

- Added focused production hardening tests for runtime ownership, memory growth, CPU/latency guardrails, thread cleanup, event bus behavior, reconnect recovery, session rollover, dashboard rendering, journal duplication protection, and secret redaction.
- Added `docs/VM_18_PRODUCTION_HARDENING_REPORT.md` with the runtime verification matrix, production risk register, and Version 1.0 readiness matrix.
- Confirmed VM-18 introduces no new trading logic, indicators, broker execution, risk changes, lifecycle changes, or journal schema changes.
