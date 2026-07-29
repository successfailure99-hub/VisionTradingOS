# Vision Method Engine V1 Architecture

Vision Method is the deterministic model of Vision's trading process. It is not
a strategy, signal generator, AI layer, risk engine, or execution component.

## Purpose

Vision Method captures the structured checklist used before any trade decision:

- CPR opening location.
- Camarilla level context.
- Previous day high, low, close, gap, and virgin CPR context.
- ADR usage and remaining range.
- VWAP relationship.
- Opening range state.
- Price action structure.
- Option chain confirmation.
- Candidate state, supporting reasons, blocking reasons, and quality.

## Runtime Position

Vision Method is a parallel methodology layer. It does not replace Fusion,
Market State, Expert Setup, Chart Explanation, AI Reasoning, Strategy, Risk, or
Paper Trading.

```text
Evidence Engines
        |
        +----> Multi-Timeframe Evidence Fusion
        |             |
        |             v
        |        Market State
        |
        +----> Vision Method
                      |
                      v
             VisionMethodSnapshot
```

## Relationship To Fusion

Fusion remains the canonical multi-timeframe agreement and conflict layer.
Vision Method may consume Fusion in a later milestone, but VM-01 introduces only
immutable models and level-context contracts. Vision Method must not recalculate
the indicators already owned by evidence engines.

## Relationship To AI

AI is not part of the methodology. AI may later consume `VisionMethodSnapshot`
to explain Vision's deterministic method, but AI must not create methodology
truth or invent trading context.

## Relationship To Strategy

Strategy remains downstream. A future StrategyDecisionV2 migration may consume
`VisionMethodSnapshot` and AI output, but VM-01 does not change strategy rules,
runtime wiring, or trade decisions.

## VM-01 Boundary

VM-01 creates only:

- immutable models;
- deterministic enums;
- validators;
- Vision Method event names;
- architecture documentation;
- focused model tests.

It intentionally does not create:

- `VisionMethodEngine`;
- calculators;
- runtime integration;
- dashboard panels;
- AI integration;
- strategy integration.

## VM-02 Level Context Boundary

VM-02 introduces deterministic level-context assembly. It consumes only existing
immutable level snapshots:

- `CPRLevels`
- `CamarillaLevels`
- `ADRSnapshot`
- `VWAPLevels`
- `DailyOHLC`

It does not calculate CPR, Camarilla, ADR, or VWAP formulas. It only classifies
where price is relative to those already-computed levels.

The level context covers:

- CPR relation: above CPR, inside CPR, below CPR.
- Camarilla zone: above H6, H5-H6, H4-H5, H3-H4, inside value, L3-L4, L4-L5,
  L5-L6, below L6.
- Previous day context: above previous high, inside previous range, below
  previous low, gap up, gap down, no gap, and supplied virgin CPR state.
- ADR context: range consumed, range remaining, ADR expansion/exhaustion, and
  proximity to ADR support or resistance.
- VWAP context: above, below, cross above, cross below, retest, reject, far
  above, and far below.

Level-context quality is deterministic:

- `FULL`: CPR, Camarilla, previous day, ADR, and VWAP are available.
- `PARTIAL`: required daily/level context is available, but optional ADR or
  VWAP evidence is missing.
- `INSUFFICIENT`: reserved for future engine-level partial handling where
  mandatory evidence is unavailable.

VM-02 still does not create a `VisionMethodEngine`, runtime integration,
dashboard panels, AI integration, strategy integration, or trade decisions.
