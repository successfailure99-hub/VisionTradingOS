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
