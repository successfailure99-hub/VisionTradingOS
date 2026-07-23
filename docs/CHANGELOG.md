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
