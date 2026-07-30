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

## VM-06 Structure Events Boundary

VM-06 introduces deterministic structure-event context. Structure explains what
price did; structure events explain when the market changed. This module
consumes:

- `VisionStructureContext` from VM-04;
- `VisionLiquidityContext` from VM-05;
- canonical immutable closed `Candle` objects.

It does not recalculate structure, liquidity, indicators, option-chain
confirmation, strategy, or AI reasoning.

The structure-event context classifies:

- bullish BOS: continuation break above a confirmed swing high after bullish
  HH/HL structure;
- bearish BOS: continuation break below a confirmed swing low after bearish
  LH/LL structure;
- bullish CHoCH: first break above structure against bearish context;
- bearish CHoCH: first break below structure against bullish context;
- MSS: descriptive market structure shift attached to CHoCH only;
- continuation, reversal, transition, or no event;
- break strength: weak, normal, strong, or none.

Break strength is deterministic and uses only structure distance, liquidity
sweep support, and recent candle range. It does not use volume, option chain,
AI, or risk. VM-06 remains non-repainting because it uses closed candles only.

VM-06 intentionally does not create runtime integration, dashboard output, AI
explanation, option confirmation, Vision Method Calculator, strategy, risk, or
execution.

## VM-07 Setup Qualification Boundary

VM-07 introduces deterministic setup qualification. It answers one question:
is there a setup worth evaluating further? It does not answer buy, sell,
position size, entry, exit, risk, or execution.

The setup qualification module consumes only existing immutable Vision Method
contexts:

- `VisionLevelContext` from VM-02;
- `VisionOpeningRangeContext` from VM-03;
- `VisionStructureContext` from VM-04;
- `VisionLiquidityContext` from VM-05;
- `VisionStructureEventContext` from VM-06.

It does not consume option-chain snapshots, AI output, StrategyDecision,
RiskManagement, runtime state, broker state, raw candles, or raw indicators.

VM-07 classifies only descriptive setup candidates:

- trend continuation;
- pullback continuation;
- breakout;
- failed breakout;
- liquidity reversal;
- range fade;
- no quality setup.

Setup quality is deterministic and limited to:

- high;
- medium;
- low;
- invalid.

The output is `VisionSetupQualificationContext`, an immutable context with:

- setup type;
- setup quality;
- blocking reasons;
- supporting reasons;
- eligibility for later option-chain confirmation.

Eligibility for option-chain confirmation is not trade eligibility. It only
means the deterministic Vision Method context deserves the next confirmation
layer. VM-07 intentionally leaves option-chain confirmation, Vision Method
Calculator, runtime integration, dashboard output, AI explanation, strategy,
risk, broker integration, and execution to later milestones.

```text
Level Context
        |
        v
Opening Range
        |
        v
Structure
        |
        v
Liquidity
        |
        v
Structure Events
        |
        v
Setup Qualification
        |
        v
Option Chain Confirmation
```

## VM-08 Option Chain Confirmation Boundary

VM-08 introduces deterministic option-chain confirmation. It answers whether
the canonical option-chain analytics confirm, partially confirm, contradict,
remain neutral, or are unavailable for an already-qualified Vision Method
setup.

The option-chain confirmation module consumes only:

- `VisionSetupQualificationContext` from VM-07;
- canonical `OptionChainSnapshot`;
- canonical `OptionChainAnalyticsSnapshot`.

It does not consume AI output, StrategyDecision, RiskManagement, runtime state,
broker state, raw candles, or raw option-chain data outside the canonical
snapshots. It does not recalculate call writing, put writing, PCR, Max Pain, OI
support, OI resistance, or OI imbalance. Those calculations remain owned by
the canonical option-chain and option-chain analytics engines.

VM-08 reuses the existing `VisionOptionConfirmation` enum created in VM-01 to
avoid duplicate confirmation vocabulary:

- confirms;
- partial;
- contradicts;
- neutral;
- unavailable.

The output is `VisionOptionConfirmationContext`, an immutable context with:

- confirmation state;
- supporting factors;
- contradicting factors;
- neutral factors;
- quality;
- timestamp.

Option Chain is a confirmation layer only. The chart-derived setup creates the
context to evaluate; option-chain analytics can only confirm, contradict, mark
mixed/partial, remain neutral, or be unavailable. VM-08 does not create trade
direction, entries, exits, order instructions, paper trades, runtime events, AI
reasoning, strategy decisions, risk decisions, or dashboard output.

## VM-09 Calculator Boundary

VM-09 introduces the Vision Method Calculator. The calculator is an assembly
layer only. It consumes the immutable contexts produced by VM-02 through VM-08:

- `VisionLevelContext`;
- `VisionOpeningRangeContext`;
- `VisionStructureContext`;
- `VisionLiquidityContext`;
- `VisionStructureEventContext`;
- `VisionSetupQualificationContext`;
- `VisionOptionConfirmationContext`.

It produces one immutable `VisionMethodSnapshot`. It does not recalculate
levels, opening range, structure, liquidity, structure events, setup
qualification, or option-chain analytics.

The calculator merges supporting and blocking reasons from the upstream
contexts, suppresses duplicates, and preserves deterministic first-seen
ordering. It classifies the existing candidate states:

- observe;
- wait;
- prepare long;
- prepare short;
- long eligible;
- short eligible;
- avoid;
- insufficient data.

Candidate state is descriptive methodology state, not execution permission.
`LONG_ELIGIBLE` and `SHORT_ELIGIBLE` mean the deterministic Vision Method
context is complete enough for downstream review. They do not place trades,
recommend orders, size positions, or enable broker activity.

Method quality is deterministic:

- `high`: complete contexts, high setup quality, and confirming option-chain
  confirmation;
- `medium`: partial or neutral confirmation, medium setup quality, or partial
  non-mandatory context;
- `low`: valid but weaker methodology context;
- `invalid`: blocking reasons, avoid state, or insufficient methodology data.

VM-09 intentionally still does not create runtime integration, dashboard
output, AI explanation, strategy decisions, risk decisions, paper trades, broker
integration, or execution. Those remain later milestones.

```text
Level Context
        |
        v
Opening Range
        |
        v
Structure
        |
        v
Liquidity
        |
        v
Structure Events
        |
        v
Setup Qualification
        |
        v
Option Chain Confirmation
        |
        v
Vision Method Calculator
        |
        v
VisionMethodSnapshot
```

## VM-10 Validation Framework Boundary

VM-10 introduces the Vision Method Validation Framework. The framework consumes
only one assembled `VisionMethodSnapshot` and produces one immutable
`VisionMethodValidationReport`.

The validation framework does not calculate levels, opening range, structure,
liquidity, structure events, setup qualification, or option-chain confirmation.
Those responsibilities remain owned by VM-02 through VM-08 and assembled by
VM-09.

The validator answers one question:

```text
Why did Vision Method reach this conclusion?
```

It emits a deterministic ordered trace:

```text
STEP 1   CPR
STEP 2   Camarilla
STEP 3   Previous Day
STEP 4   ADR
STEP 5   VWAP
STEP 6   Opening Range
STEP 7   Structure
STEP 8   Liquidity
STEP 9   Setup
STEP 10  Option Chain
FINAL    Candidate State
```

Every trace step records:

- stage;
- observed value;
- status: pass, fail, or missing;
- optional detail.

The report also records deterministic metrics:

- completed steps;
- failed steps;
- missing steps;
- confidence inputs;
- blocking stage.

Validation results are descriptive:

- `VALID`;
- `PARTIAL`;
- `INVALID`;
- `CONFLICT`;
- `INSUFFICIENT_DATA`.

No probabilities are produced. `confidence_inputs` are the deterministic
supporting reasons carried by the assembled methodology snapshot, not numeric
confidence scores.

The validation report is replay-ready: a historical replay can generate one
report for every closed candle after a `VisionMethodSnapshot` exists. The
report includes an export-ready immutable record suitable for later CSV or JSON
serialization. VM-10 does not write files.

VM-10 intentionally does not create runtime integration, dashboard output, AI
explanation, strategy decisions, risk decisions, paper trades, broker
integration, or execution.

```text
VisionMethodSnapshot
        |
        v
Vision Method Validation Framework
        |
        v
VisionMethodValidationReport
```

## VM-11 Vision Method Inspector Boundary

VM-11 introduces the Vision Method Inspector. The inspector is a read-only
desktop presentation layer for the deterministic Vision Method output.

It consumes only:

- `VisionMethodSnapshot`;
- `VisionMethodValidationReport`.

It does not recalculate levels, opening range, structure, liquidity, structure
events, setup qualification, option-chain confirmation, candidate state,
quality, validation result, or validation metrics.

The inspector exists to answer:

```text
Does Vision Trading OS think exactly like Vision?
```

The desktop application exposes a top-level `Vision Method` tab. The tab starts
in an unavailable state until a snapshot and report are supplied by a later
runtime or replay workflow. VM-11 does not create that workflow.

The inspector displays the deterministic methodology layers:

- header and candidate state;
- level context;
- opening range;
- structure;
- structure events;
- liquidity;
- setup qualification;
- option confirmation;
- Vision Method candidate state and method quality;
- validation result and metrics;
- full validation trace in order.

If a field is not present in the immutable snapshot or validation report, the
inspector shows a placeholder rather than deriving or fabricating it. This keeps
the desktop view faithful to the methodology data that actually exists.

VM-11 intentionally does not create runtime integration, paper trading
integration, AI changes, strategy changes, risk changes, broker execution, or a
dashboard redesign.

```text
VisionMethodSnapshot
VisionMethodValidationReport
        |
        v
Vision Method Inspector
        |
        v
Read-only desktop tab
```

## VM-11.1 Vision Method Live Inspector Integration

VM-11.1 connects the read-only desktop inspector to the existing deterministic
Vision Method pipeline. It is a presentation bridge, not a new runtime engine.

The bridge reads the existing symbol runtime state and closed candle history,
then invokes the already-certified Vision Method components in order:

```text
Market data already held by runtime
        |
        v
Vision Method context assemblers
        |
        v
VisionMethodCalculator
        |
        v
VisionMethodValidation
        |
        v
VisionMethodInspector
```

The bridge reuses:

- `VisionLevelContextRequest` and `assemble_vision_level_context`;
- `VisionOpeningRangeRequest` and `assemble_vision_opening_range_context`;
- `VisionStructureRequest` and `assemble_vision_structure_context`;
- `VisionLiquidityRequest` and `assemble_vision_liquidity_context`;
- `VisionStructureEventRequest` and `assemble_vision_structure_event_context`;
- `VisionSetupQualificationRequest` and
  `assemble_vision_setup_qualification_context`;
- `VisionOptionConfirmationRequest` and
  `assemble_vision_option_confirmation_context`;
- `VisionMethodCalculationRequest` and `calculate_vision_method_snapshot`;
- `validate_vision_method`.

Before market data has produced any timestamp, the inspector remains in its
unavailable placeholder state. Once market data has started, expected assembly
failures are surfaced as deterministic status instead of blanking the whole
panel. The inspector shows the failed stage, failure status, and validation
message while preserving all contexts that were assembled successfully.

When optional evidence such as ADR, VWAP, or option-chain analytics is missing,
the existing Vision Method contexts report that as unavailable or insufficient
instead of the inspector fabricating values.

VM-11.1 adds debug-only lifecycle messages:

```text
[VisionMethod] Snapshot generated
[VisionMethod] Validation complete
[VisionMethod] Inspector updated
```

The integration does not continue into trade candidate generation, AI,
Strategy, Risk, Paper Trading, broker order placement, or execution. It does
not publish events, create runtime ownership, or add a second Vision Method
calculation pipeline.

## VM-11.2 Fault-Tolerant Context Assembly

VM-11.2 keeps strict Vision Method context validation intact. It does not weaken
Liquidity, Fair Value Gap detection, setup qualification, option-chain
confirmation, or any trading rule.

The live inspector bridge now converts expected context assembly failures into
immutable `VisionContextAssemblyFailure` records containing:

- stage;
- status;
- failure reason;
- validation message.

Where a failed stage can be represented safely, the bridge supplies an
insufficient fallback context and passes the failure record into
`VisionMethodCalculator`. The resulting `VisionMethodSnapshot` has
`candidate_state=INSUFFICIENT_DATA`, carries the assembly failures, and produces
a validation report that identifies the failed stage in the trace.

If a foundational prerequisite is missing before a snapshot can be honestly
assembled, such as CPR or closed candle history, the inspector renders a
deterministic failure state with `INSUFFICIENT_DATA` instead of staying blank
after market data has started.

```text
Context A succeeds
Context B fails validation
Context C depends on B and reports unavailable
        |
        v
Inspector shows A plus exact B/C failure reasons
```

The strict context assemblers still raise their original validation exceptions.
The bridge converts those exceptions at the presentation boundary so no expected
single-stage failure can hide the rest of the deterministic methodology view.

## VM-11.3 End-to-End Inspector Reliability

VM-11.3 formalizes the live inspector as a state machine. The inspector must
never show an unexplained screen of placeholder values after startup. Every
live refresh renders one immutable `VisionMethodLiveStatus` alongside any
available `VisionMethodSnapshot` and `VisionMethodValidationReport`.

The live runtime states are:

- `WAITING_FOR_MARKET_DATA`: no market timestamp exists yet.
- `COLLECTING_CONTEXT`: market data exists but one or more expected contexts
  are still unavailable or incomplete.
- `DEGRADED`: at least one context assembly failed, but the bridge preserved
  the available upstream contexts and rendered the failure reason.
- `READY`: a valid methodology snapshot and validation report are available.
- `INTERNAL_ERROR`: an unexpected programming defect occurred and was surfaced
  explicitly.

The inspector status panel records:

- runtime state;
- last market update;
- last inspector refresh;
- market data age;
- instrument and timeframe;
- blocking stage;
- blocking reason;
- available contexts;
- missing contexts;
- failed contexts;
- unexpected error.

The context status meanings are:

- `MISSING`: required data is expected but not yet available, such as no closed
  candle history or missing daily CPR levels.
- `NOT_EVALUATED`: a downstream context was skipped because its real
  dependency was unavailable.
- `FAILED`: a context assembler ran and rejected its inputs through its normal
  validation rules.

Expected operational states, including no live tick, no closed candle, missing
daily levels, incomplete opening range, unavailable option chain, or a normal
Vision Method validation failure, must not clear the inspector. They render
explicit diagnostic values instead.

```text
MainWindow refresh
        |
        v
VisionMethodLiveInspectorBridge.refresh()
        |
        +----> VisionMethodLiveStatus
        +----> VisionMethodSnapshot, when honestly available
        +----> VisionMethodValidationReport, when validation succeeds
        |
        v
Visible VisionMethodInspector instance
```

The bridge does not publish events, own runtime state, trigger Strategy,
trigger AI, run Risk, update Paper Trading, or modify broker execution. It is
only an observability adapter for deterministic Vision Method data.

## VM-11.4 Trading Session Synchronization

VM-11.4 adds an explicit pre-assembly session gate for live Vision Method
inspection. Before the bridge creates a `VisionLevelContextRequest`, mandatory
daily contexts must belong to the active market session derived from the latest
market timestamp.

The gate verifies:

- market timestamp session date;
- CPR trading date;
- Camarilla trading date;
- previous-day reference derived from the accepted CPR levels;
- optional ADR trading date;
- optional VWAP trading date.

If CPR or Camarilla belongs to a different session, the bridge does not call
the Vision Method calculator and does not surface the validator exception as an
internal error. It renders `COLLECTING_CONTEXT` with the exact blocking stage
and reason, for example:

```text
Runtime State   COLLECTING_CONTEXT
Blocking Stage  CPR
Reason          CPR belongs to previous trading session.
```

Optional ADR or VWAP session mismatches are omitted from the level request and
recorded as missing context. The rest of the available Vision Method contexts
continue to assemble wherever their dependencies allow.

The underlying CPR, Camarilla, ADR, VWAP, level-context validation, Liquidity,
Structure, Opening Range, and trading rules remain unchanged. VM-11.4 only
synchronizes live context ownership before assembly so the inspector waits for
the daily-context refresh instead of treating expected session drift as a
programming failure.
