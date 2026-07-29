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

## VM-03 Opening Range Boundary

VM-03 introduces deterministic opening-range context. It consumes only
canonical immutable closed `Candle` objects and observes the Vision Method
opening window:

- session open: 09:15;
- opening range end: 09:30;
- opening high: maximum candle high between 09:15 and 09:30;
- opening low: minimum candle low between 09:15 and 09:30;
- opening width: opening high minus opening low.

Before 09:30, the opening range remains incomplete and the context is
`WAITING`. After 09:30, the opening high and opening low are frozen for the
trading day. Later candles can only classify where price is relative to that
frozen range:

- inside range;
- break above;
- break below;
- retest;
- false break.

Opening Range is context only. It does not calculate structure, BOS, CHoCH,
liquidity, FVG, order blocks, option confirmation, AI reasoning, strategy, risk,
or trade decisions.

VM-03 still does not create a `VisionMethodEngine`, runtime integration,
dashboard panels, AI integration, strategy integration, or trade decisions.

## VM-04 Structure Boundary

VM-04 introduces deterministic structural swing context. It consumes only
canonical immutable closed `Candle` objects. Price structure is treated as the
foundation of the Vision Method; CPR, Camarilla, VWAP, ADR, AI, and Option
Chain are overlays or confirmations and do not create structure.

The structure module confirms swing points with configurable left/right bars:

- default left bars: 2;
- default right bars: 2;
- strict swing high: candidate high is greater than all left/right highs;
- strict swing low: candidate low is lower than all left/right lows;
- a candidate is not confirmed until the required right bars exist.

This produces non-repainting confirmed swings. VM-04 records:

- current swing high;
- current swing low;
- previous swing high;
- previous swing low;
- last confirmed swing;
- structural trend: bullish, bearish, ranging, unknown;
- latest structural pattern: HH, HL, LH, LL, unknown.

VM-04 intentionally does not classify Break of Structure, Change of Character,
Market Structure Shift, liquidity sweeps, equal highs/lows, Fair Value Gaps,
order blocks, entries, exits, strategy, AI, runtime, or dashboard output. Those
belong to later Vision Method milestones.

## VM-05 Liquidity Boundary

VM-05 introduces deterministic liquidity context. It consumes only canonical
immutable closed `Candle` objects. Within the Vision Method, structure explains
what price did, while liquidity explains why price may have moved.

The liquidity module classifies:

- equal highs using configurable tolerance, defaulting to 0.05%;
- equal lows using the same tolerance;
- buy-side, sell-side, or no visible liquidity pool;
- buy-side and sell-side liquidity sweeps where price trades beyond an equal
  high or equal low and then closes back inside;
- three-candle Fair Value Gaps as descriptive imbalance context;
- an initial order-block marker as the last opposite candle before an impulsive
  move;
- breaker block and mitigation fields as immutable placeholders only.

VM-05 remains non-repainting because it uses closed candles only. It does not
refine order blocks, evaluate mitigation, create setup eligibility, confirm
with option chain data, publish runtime events, update dashboard panels, call AI,
or produce trade decisions.

VM-05 intentionally does not implement BOS, CHoCH, Market Structure Shift,
Vision Method Calculator, runtime integration, dashboard output, AI explanation,
strategy, risk, or execution. Those belong to later Vision Method milestones.
