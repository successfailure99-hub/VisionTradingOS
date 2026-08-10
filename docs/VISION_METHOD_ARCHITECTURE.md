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

Fair Value Gap handling follows a deterministic normalization policy before
model validation:

- exact duplicate gaps are removed;
- same-direction overlapping or touching gaps are merged into one outer zone;
- nested same-direction gaps merge into the containing zone;
- opposite-direction overlaps are retained as conflicting market context and
  must not crash live assembly;
- invalid numeric bounds and invalid candle sequences remain validation errors.

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
- optional `VisionLiquidityContext` from VM-05;
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

Break strength is deterministic and uses only structure distance, available
liquidity sweep support, and recent candle range. BOS and CHoCH remain
structure-driven, so they may still be evaluated if liquidity is unavailable or
insufficient. Liquidity-dependent support simply remains neutral for that field.
It does not use volume, option chain, AI, or risk. VM-06 remains non-repainting
because it uses closed candles only.

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

Runtime daily context production uses the previous completed trading session as
the price source for same-day levels. The stored `DailyOHLC` keeps its original
completed-session trading date, while CPR and Camarilla level snapshots are
created for the active market session before Vision Method level assembly. This
preserves the existing CPR and Camarilla formulas and fixes only the runtime
session ownership of the produced level snapshots.

If previous completed-session OHLC is unavailable at startup, the Vision Method
runtime state remains `WAITING_DAILY_CONTEXT` with blocking stage
`DAILY_OHLC`. The runtime retries through the normal warm-up/recovery path and
does not repeatedly rebuild daily context from dashboard repaints.

## VM-11.5 Independent Context Assembly

VM-11.5 changes the live inspector bridge from all-or-nothing assembly to
dependency-aware independent assembly. A missing mandatory daily context, such
as CPR, no longer hides unrelated contexts that can be evaluated from closed
candles.

The live assembly graph is:

```text
Market Data
        |
        +----> Level Context
        +----> Opening Range
        +----> Structure
        +----> Liquidity
        +----> Structure Events
        +----> Setup Qualification
        +----> Option Confirmation
```

Each context runs only when its own prerequisites are available:

- Level Context requires session-aligned CPR and Camarilla. Optional ADR and
  VWAP mismatches are recorded as missing and omitted from the level request.
- Opening Range requires only instrument, timeframe, session date, timestamp,
  and closed candles.
- Structure requires only sufficient closed candles.
- Liquidity requires only sufficient closed candles and its canonical
  liquidity rules.
- Structure Events require valid Structure and Liquidity contexts.
- Setup Qualification requires Level Context, Opening Range, Structure,
  Liquidity, and Structure Events.
- Option Confirmation requires Setup Qualification and canonical option-chain
  inputs. If Setup Qualification is unavailable, Option Confirmation is marked
  `NOT_EVALUATED`; if option-chain data is absent after setup exists, it is
  `UNAVAILABLE`.

Context states are:

- `AVAILABLE`: a valid immutable context exists.
- `MISSING`: required input is absent or belongs to another trading session.
- `FAILED`: the assembler executed and rejected its inputs.
- `NOT_EVALUATED`: a real dependency was unavailable.
- `UNAVAILABLE`: an external source, such as option-chain data, is not present.

The final methodology state remains safe. If any mandatory context is missing
or incomplete, the live status reports:

```text
Candidate State    insufficient_data
Quality            invalid
Validation Result  insufficient_data
```

The bridge does not fabricate a full `VisionMethodSnapshot` from incomplete
mandatory contexts. It carries successful independent contexts in
`VisionMethodLiveStatus` so the inspector can show what the system knows while
still blocking actionable candidate states.

## VM-12 Vision Runtime Adapter

VM-12 introduces the non-executing boundary between the completed Vision Method
and later trading subsystems.

```text
VisionMethodSnapshot
        |
        v
VisionRuntimeAdapter
        |
        v
TradeCandidate
```

The adapter consumes only:

- `VisionMethodSnapshot`
- `VisionMethodValidationReport`

It does not consume indicators, AI reasoning, strategy, risk, broker state,
paper trading state, or execution state. It does not calculate order prices,
position size, stop-loss prices, targets, risk, or probability. It converts the
Vision Method candidate state into a standardized immutable candidate contract
that later milestones can route into paper trading or risk review.

Candidate mapping is deterministic:

- `LONG_ELIGIBLE` -> `LONG`
- `SHORT_ELIGIBLE` -> `SHORT`
- `PREPARE_LONG` -> `WAITING_LONG`
- `PREPARE_SHORT` -> `WAITING_SHORT`
- `WAIT`, `OBSERVE`, `AVOID`, and `INSUFFICIENT_DATA` -> `NO_CANDIDATE`

`TradeCandidate` contains only references. Entry, stop-loss, and target fields
are named structural zones such as `Opening Range Break`, `Below Swing Low`,
`Above Swing High`, `H4`, `L4`, `Previous High`, or `ADR Low`. They are not
broker-ready order prices.

The adapter preserves auditability through deterministic source references:

- `snapshot_reference` points to the Vision Method snapshot identity.
- `validation_reference` points to the validation report identity.

VM-12 intentionally stops here. It does not send the candidate to Strategy,
Risk, Paper Trading, Broker, or AI. Future milestones may consume
`TradeCandidate`, but this milestone only creates the immutable handoff
contract.

## VM-13 Vision Paper Trading Integration

VM-13 routes completed Vision Method candidates into the existing dry-run paper
trading stack without introducing a new lifecycle or changing certified
strategy, risk, broker, or execution rules.

```text
VisionMethodSnapshot
        |
        v
VisionMethodValidationReport
        |
        v
VisionRuntimeAdapter
        |
        v
TradeCandidate
        |
        v
RiskManagementV2
        |
        v
TradeLifecycleV1
        |
        v
TradeJournalV1
```

Only actionable candidates are forwarded to risk review:

- `TradeCandidateState.LONG` with `TradeCandidateDirection.LONG`
- `TradeCandidateState.SHORT` with `TradeCandidateDirection.SHORT`

The following Vision Method states remain observational and are blocked before
risk review:

- `WAIT`
- `OBSERVE`
- `AVOID`
- `INSUFFICIENT_DATA`
- `PREPARE_LONG`
- `PREPARE_SHORT`

The runtime preserves the existing Risk V2 and Trade Lifecycle V1 contracts by
creating a StrategyDecisionV2-compatible handoff snapshot with explicit
`trade_source = "VISION_METHOD"` metadata. The StrategyDecisionV2 engine is not
asked to reinterpret the candidate, and no strategy decision rules are changed.

Journal entries store references, not duplicated snapshots:

- `trade_candidate_reference`
- `vision_method_snapshot_reference`
- `vision_method_validation_reference`

The dashboard journal panel displays the trade source for completed dry-run
trades. VM-13 does not place broker orders, enable live trading, modify AI
reasoning, or redesign Paper Trading.

## VM-13.3 Runtime Ownership Contract

VM-13.3 completes the runtime ownership boundary for the Vision Method live
path. `SymbolRuntime` is the single owner of:

- the canonical market timestamp;
- the active trading-session snapshot;
- the Vision Method snapshot reference;
- the Vision Method validation report reference;
- the latest `TradeCandidate`;
- the decision audit;
- the runtime verification report.

The canonical market timestamp is derived from runtime market data in priority
order:

1. latest closed candle timestamp;
2. latest accepted tick timestamp;
3. latest candle end timestamp;
4. last accepted runtime update timestamp.

Trading engines must consume this runtime market timestamp rather than
independent wall-clock refresh timestamps. Dashboard rendering may still use a
UI clock for display freshness, but that clock is not market truth.

The runtime trading session is represented by one immutable
`RuntimeTradingSession` snapshot. It records the active trading date, previous
completed-session source date, CPR date, Camarilla date, optional ADR date, and
optional VWAP date. CPR and Camarilla are considered ready only when their
level snapshots belong to the active trading date.

The runtime verification report is an ordered, immutable ownership matrix. Each
stage records:

- owner;
- producer;
- consumer;
- canonical timestamp;
- session;
- status;
- blocking reason.

The dashboard reads this report from the runtime snapshot. It does not calculate
Vision Method state, infer ownership, or keep an independent cache of the
Vision pipeline.

## VM-14 Paper Trading Runtime Unification

VM-14 makes `SymbolRuntime` the canonical owner of Vision Method paper-trading
state. The older plan-based `PaperTradingEngine` remains available for legacy
trade-plan compatibility, but it is not the primary Vision Method paper-position
source.

Canonical Vision paper flow:

```text
VisionMethodSnapshot
        |
        v
VisionMethodValidationReport
        |
        v
TradeCandidate
        |
        v
RiskManagementV2Snapshot
        |
        v
TradeLifecycleV1
        |
        v
PositionManagementV1
        |
        v
RuntimePaperPositionSnapshot
        |
        v
TradeJournalV1
        |
        v
RuntimeSnapshot / Dashboard
```

Ownership after VM-14:

| Concern | Canonical owner |
| --- | --- |
| Paper order request | TradeLifecycleV1 / ExecutionRuntimeV1 dry-run intent |
| Fill simulation | ExecutionRuntimeV1 dry-run simulator |
| Open paper position | PositionManagementV1, exposed by SymbolRuntime |
| Stop/target processing | PositionManagementV1 via TradeLifecycleV1 price updates |
| Position closure | TradeLifecycleV1 / PositionManagementV1 |
| P&L | PositionManagementV1 |
| Fees/slippage | Not modeled by Lifecycle V1; exposed as `0.0` on the canonical snapshot until VM-15+ defines durable accounting |
| Journal write | TradeJournalV1 |
| Dashboard status | RuntimeSnapshot.canonical_paper_position |
| Restart recovery | VM-15 durable checkpoint policy: `NO_POSITION`, `RESTORED`, `RECOVERY_BLOCKED`, `RECOVERY_FAILED`, or `CLOSED_BEFORE_SHUTDOWN` |

`RuntimePaperPositionSnapshot` is immutable and reference-based. It preserves the
TradeCandidate, Vision Method snapshot, validation report, and risk references
without duplicating the underlying snapshots.

Every actionable Vision candidate is identified by a deterministic candidate
identity. Repeated dashboard refreshes, duplicate candidate submissions, and
reconnect callbacks reuse the existing lifecycle state instead of opening a
second paper position.

Dashboard position panels must prefer `RuntimeSnapshot.canonical_paper_position`
whenever present. Legacy paper-trading status may still be displayed only when no
canonical Vision paper position exists.

## VM-15 Vision Analytics Journal & Durable Paper Recovery

VM-15 makes the Vision Method paper-trading path durable without changing trading rules, risk calculations, lifecycle rules, or paper fill behavior.

Canonical ownership after VM-15:

| Concern | Current owner | Canonical owner after VM-15 |
| --- | --- | --- |
| Journal record creation | `TradeJournalEntryBuilder` | `TradeJournalV1Engine` using `TradeJournalEntryBuilder` |
| Journal persistence | none / in-memory registry | `TradeJournalPersistence` append-only JSONL |
| Open paper-position checkpoint | none | `TradeJournalPersistence` atomic checkpoint file |
| Closed-trade record | `TradeJournalRegistry` | `TradeJournalRegistry` plus durable `VisionTradeJournalRecord` |
| Duplicate suppression | `TradeJournalRegistry` | `TradeJournalRegistry` plus durable trade-id check |
| Search/filter | in-memory entries | streaming `TradeJournalQuery` over durable JSONL |
| Replay lookup | journal entry references | compact Vision, validation, candidate, risk, lifecycle, and paper-position references |
| Restart recovery | `NOT_DURABLE` | deterministic `PaperRecoverySnapshot` |
| Performance summaries | `TradePerformanceAnalyticsCalculator` | unchanged; fed once from completed journal entries |

### Canonical Journal Schema

The durable `VisionTradeJournalRecord` stores compact immutable trade evidence rather than copying large snapshot graphs. It contains the trade identity, instrument, exchange, timeframe, trading date, Vision Method references, validation references, trade candidate reference, risk reference, lifecycle reference, paper-position reference, setup classification, candidate direction and quality, validation result, entry/exit prices, quantity, stop/target prices, gross P&L, fees, slippage, net P&L, timestamps, and schema version.

Retention policy: completed Vision paper records are append-only JSONL. Runtime queries stream records and malformed lines are isolated so one bad row cannot prevent valid records from being read.

### Checkpoint Schema

The active paper checkpoint stores exactly one open Vision paper position per instrument path. It includes trade ID, candidate identity, instrument, direction, entry, quantity, stop, target, last market timestamp, lifecycle state, position state, unrealized P&L, Vision references, risk reference, and checkpoint version. Writes use an atomic replace policy.

### Restart And Session Recovery

Recovery outcomes are deterministic:

- `NO_POSITION`: no checkpoint exists.
- `RESTORED`: checkpoint matches the expected instrument and trading session.
- `RECOVERY_BLOCKED`: checkpoint exists but fails ownership validation.
- `RECOVERY_FAILED`: checkpoint is malformed or unreadable.
- `CLOSED_BEFORE_SHUTDOWN`: checkpoint belongs to an older trading session and must not be silently carried forward.

Broker orders are never replayed. Recovery is paper-only.

### Duplicate Prevention

Exactly-once completed journal writes are protected by stable `trade_id`, candidate identity, lifecycle identity, and durable duplicate checks. Repeated close ticks, reconnects, dashboard refreshes, and duplicate lifecycle routing must not append a second durable record.

### Security

Durable journal records and checkpoints must not serialize access tokens, API keys, credentials, passwords, or broker secrets. The persistence layer rejects payloads containing sensitive field names before writing.

## VM-16 Live Session Validation and Dashboard Finalization

VM-16 certifies the existing Vision Method runtime as the dashboard-facing production workstation. It does not add trading logic, indicators, broker execution, AI rules, or strategy behavior.

The canonical live-session sequence is:

Application Startup
-> Reference Data Warmup
-> Daily Context
-> Market Data
-> Candle Engine
-> Opening Range
-> Structure
-> Liquidity
-> Structure Events
-> Setup Qualification
-> Option Confirmation
-> Vision Method
-> Validation
-> Runtime Adapter
-> TradeCandidate
-> Risk
-> Lifecycle
-> Paper Position
-> Journal
-> AI Explanation
-> Dashboard

`SymbolRuntime` remains the single owner of the production runtime snapshot. Dashboard panels consume `RuntimeSnapshot` and its immutable child snapshots only. They must not calculate Vision Method state, risk, paper trading state, journal state, or AI explanation text.

Each runtime verification row exposes owner, producer, consumer, timestamp, trading session, status, latency, recovery state, and blocking reason. This lets the dashboard show `READY`, `WAITING`, `BLOCKED`, or `FAILED` for every production stage without reading logs or maintaining a second cache.

Session rollover requires the active runtime trading date to match CPR and Camarilla trading dates before Vision Method evaluation is considered ready. If daily context is missing or stale, the runtime reports `WAITING_DAILY_CONTEXT` and blocks Vision Method readiness until fresh daily context is available.

## VM-17 Broker Account Boundary

Vision Method remains the deterministic methodology source. VM-17 does not change Vision Method calculations, candidate generation, risk, lifecycle, paper trading, or AI behavior. It adds a read-only account observability boundary downstream of the runtime so the workstation can see broker account health without enabling execution.

```text
Broker Authentication
        |
        v
Read-Only Broker Account Sync
        |
        v
BrokerAccountSnapshot
        |
        v
OrchestratorSnapshot -> Dashboard Runtime Health
```

The account snapshot is account-wide and owned by `ApplicationOrchestrator`, not by individual symbol runtimes. It may reconcile broker positions with paper positions for observability, but it must not create trades, alter Vision Method state, or mutate broker state.

## VPM-CONTEXT-1 Pivot Flight Plan Boundary

VPM-CONTEXT-1 adds a deterministic pre-market pivot context layer to the Vision
Method. The layer compares active-session CPR and Camarilla value areas against
the prior completed session's pivot context and classifies only the morning
roadmap.

The Pivot Flight Plan consumes:

- active-session `CPRLevels`;
- active-session `CamarillaLevels`;
- completed-session `DailyOHLC` history.

It does not consume ticks, live candles, AI, Strategy, Risk, broker state, paper
trading, or option execution. It does not duplicate CPR or Camarilla formulas;
historical comparison uses the canonical CPR and Camarilla calculators.

The context classifies CPR relationship, Camarilla H3-L3 relationship, CPR
width, Camarilla width, combined pivot context, provisional directional prior,
expansion tendency, balance tendency, and conditional bullish/bearish action
zones.

H6 and L6 are deliberately excluded from relationship and width intelligence.
They remain outer reference levels, not the primary two-day value relationship.

All Pivot Flight Plans are provisional. They always carry
`opening_confirmation_required=True`; opening acceptance, rejection, trigger
logic, candidate promotion, option-selling selection, Strategy, Risk, and Paper
Trading remain downstream and unchanged. A flight plan may be displayed in the
Inspector and forensic trace, but it must never create a `TradeCandidate` by
itself.
