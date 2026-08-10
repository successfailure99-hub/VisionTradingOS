# VPM-1 — Complete Pivot Methodology Extraction & Vision Blueprint
## VISION_PIVOT_METHOD_V1

**Source basis:** Franklin O. Ochoa Jr., *Secrets of a Pivot Boss* (complete-book review, 388 pages).
**Project:** Vision Trading OS
**Status:** Methodology blueprint only — **NO production code change**
**Purpose:** Convert the book's price/pivot framework into a deterministic reasoning hierarchy for Vision Trading OS without blindly copying isolated rules.

---

## 1. Core Philosophy Extracted From the Book

The book is not a collection of mechanical “touch a level = trade” rules. Its recurring framework is:

1. Understand the market auction and identify whether behavior is responsive or initiative.
2. Diagnose the probable market-day type and current trend.
3. Determine value/location using price-based pivots.
4. Form a pre-market directional or behavioral hypothesis.
5. Let the opening print and early price action accept or reject that hypothesis.
6. Wait for price to reach an important action zone.
7. Use price behavior/candlestick structure as the trigger.
8. Set entry, invalidation and target **before** executing.
9. Adjust target/holding expectations to pivot width/day type.
10. Stand aside when conditions are not favorable.

**Vision translation:** Context → Location → Event → Confirmation → Asymmetry → Execution.

---

# PART A — MARKET AUCTION & DAY-TYPE INTELLIGENCE

## 2. Responsive vs Initiative Activity

### Responsive Buyers
- Act when price is perceived below value.
- Push price back toward fair value.
- More associated with reversals/fades.

### Responsive Sellers
- Act when price is perceived above value.
- Push price back toward fair value.
- More associated with reversals/fades.

### Initiative Buyers
- Buy at/above value to establish higher value.
- Create conviction, range extension and trend behavior.

### Initiative Sellers
- Sell at/below value to establish lower value.
- Create conviction, range extension and trend behavior.

### Vision rule
Every pivot reaction should be classified conceptually as:
- `RESPONSIVE_REVERSAL`
- `INITIATIVE_BREAKOUT`
- `UNRESOLVED_TEST`

A pivot touch without evidence of who is winning is **not an entry**.

---

## 3. Market-Day Types

Book day types:

1. Trend Day
2. Double-Distribution Trend Day
3. Typical Day
4. Expanded Typical Day
5. Trading Range Day
6. Sideways Day

### Vision purpose
Day type is not a rigid prediction; it is a live hypothesis that changes what setups deserve attention.

### Trend Day
Characteristics:
- Strong directional conviction.
- Often opens near one extreme and closes near the opposite extreme.
- Initiative participants dominate.
- Larger-than-normal range.
- Often follows quiet/consolidating behavior.

Preferred tactics:
- Join direction early.
- Buy pullbacks in bullish trend / sell rallies in bearish trend.
- Avoid repeatedly fading the trend.
- Wider trailing logic / larger destination expectations.

### Double-Distribution Trend Day
Characteristics:
- Quiet initial balance.
- Breakout/range extension after early balance.
- New distribution develops at new value.

Preferred tactics:
- Wait for initiative break.
- Retest/acceptance can provide entry.

### Typical Day
Characteristics:
- Strong early move creates wide initial balance.
- Responsive counterparties establish extremes.
- Later trade tends to remain within those extremes.

Preferred tactics:
- Responsive reversal setups at extremes.
- More moderate targets.

### Expanded Typical Day
Characteristics:
- Moderate initial balance.
- One extreme later breaks.
- Directional expansion can follow.

### Trading Range Day
Characteristics:
- Active two-way trade.
- Responsive buyers/sellers operate at extremes.
- Range fades can work.

### Sideways Day
Characteristics:
- Low conviction and poor participation.
- Narrow activity without initiative breakout.
- Often a **no-trade** environment.

### Critical Vision principle
`NOT EVERY DAY MUST PRODUCE A TRADE`.

---

# PART B — PRICE-ACTION TRIGGERS

## 4. Wick Reversal

Book characteristics:
- Wick size traditionally at least 2:1 to body.
- Author prefers roughly 2.5:1 to 3.5:1 in many examples.
- Bullish reversal should close toward upper part of candle.
- Bearish reversal should close toward lower part.
- Location is essential.
- A wick signal alone is not automatically a warranted trade.

### Vision role
Use only as a **trigger at an action zone**, not as a standalone trade generator.

Suggested semantic outputs:
- `BULLISH_REJECTION`
- `BEARISH_REJECTION`
- `WEAK_REJECTION`
- `NO_REJECTION`

Do not blindly transplant exact wick-ratio tuning without later NIFTY validation.

---

## 5. Extreme Reversal

Concept:
- First candle unusually large relative to recent bars.
- Second candle fails continuation and opposes first.
- Represents overextension and responsive snapback.

Best uses:
- Early-session overextension.
- Pullback in direction of an existing trend.
- Avoid fighting an aggressive trend merely because pattern exists.

### Vision role
Useful for:
- `MOVE_EXHAUSTION`
- `RESPONSIVE_REVERSAL`
- `PULLBACK_COMPLETION`

---

## 6. Outside Reversal

Bullish concept:
- Current low below prior low.
- Current close above prior high.

Bearish concept:
- Current high above prior high.
- Current close below prior low.

Represents a failed auction beyond support/resistance followed by decisive rejection.

### Vision role
Strong trigger for:
- failed breakout
- liquidity sweep
- rejection
- reversal at pivot/hot zone

---

## 7. Doji Reversal

Book principle:
- Doji = indecision, not an entry by itself.
- Context/trend/location matter.
- Confirmation from subsequent closing behavior improves validity.
- Author prefers higher timeframe for this pattern.

### Vision role
Use as:
- `INDECISION_AT_ACTION_ZONE`
- supporting reversal evidence
not as standalone eligibility.

---

# PART C — CPR / CENTRAL PIVOT RANGE

## 8. CPR Formula & Ownership

Book CPR:
- Pivot = (High + Low + Close) / 3
- BC = (High + Low) / 2
- TC = (Pivot - BC) + Pivot
- Highest outer value is TC and lowest outer value is BC in final display.

Vision already owns formula implementation.

**Do not change CPR math in VPM-1.**

---

## 9. CPR Functions in the Book

CPR can act as:
- support
- resistance
- directional bias
- trend framework
- gap magnet
- trend pullback location
- width/day-type forecast
- two-day relationship framework

Vision should not treat CPR as merely three plotted lines.

---

## 10. Two-Day CPR Relationships

Seven relationships:

### 10.1 Higher Value
Current CPR completely above prior CPR.

Bias:
- Bullish.

Acceptance:
- Prior close and current open in supportive location.
- Pullbacks to CPR can be buying opportunities.

Rejection:
- Opening below the expected bullish area can invalidate/reverse the initial thesis.

### 10.2 Overlapping Higher Value
Current CPR higher but overlaps prior CPR.

Bias:
- Moderately bullish.
- Less conviction than Higher Value.

### 10.3 Lower Value
Current CPR completely below prior CPR.

Bias:
- Bearish.

Acceptance:
- Open below CPR supports selling pullbacks to CPR.

Rejection:
- Strong open above CPR / prior range can flip interpretation bullish.

### 10.4 Overlapping Lower Value
Current CPR lower but overlaps prior CPR.

Bias:
- Moderately bearish.

### 10.5 Unchanged Value
Current CPR essentially unchanged.

Possible behavior:
- continued balance/range
OR
- breakout if opening/location shows initiative behavior.

The opening print is crucial.

### 10.6 Outside Value
Current CPR engulfs prior CPR.

Expected:
- Sideways / Trading Range tendency.
- Particularly informative when current CPR is also significantly wider.

### 10.7 Inside Value
Current CPR lies inside prior CPR.

Expected:
- Breakout potential.
- Strongest when current CPR is much narrower than prior CPR.
- Opening beyond prior range adds major confirmation.

---

## 11. CPR Acceptance / Rejection

A pre-market CPR forecast is **not final**.

Vision must model:

`EXPECTED_BIAS`
→ opening print
→ `ACCEPTED`
or
→ `REJECTED`

Example:
- Lower Value CPR predicts bearishness.
- Open below CPR = acceptance.
- Open strongly above CPR/prior range = rejection and possible bullish regime shift.

This is a first-class reasoning event, not a cosmetic field.

---

## 12. CPR Width

### Narrow CPR
Book expectation:
- Increased probability of breakout/trending behavior.
- Especially strong when prior session was quiet.
- Opening beyond prior range strengthens breakout thesis.

### Wide CPR
Book expectation:
- More likely range/sideways behavior.
- Reduce target expectations.
- Consider smaller swings or standing aside.

### Average CPR
- Little predictive edge from width alone.

### Vision rule
Width is a **day-type prior**, not an entry trigger.

---

## 13. CPR Trend Analysis

Book principle:
- In uptrend, CPR often acts as support.
- In downtrend, CPR often acts as resistance.
- Pullbacks to CPR in established trend can be high-quality entries.
- Strong bullish trends often remain above BC.
- Strong bearish trends often remain below TC.
- A meaningful close through the opposite side can indicate trend transition.

### Vision translation

Bullish trend:
- Prefer `BUY_THE_DIP` logic at CPR support.

Bearish trend:
- Prefer `SELL_THE_RIP` logic at CPR resistance.

Do not automatically countertrend fade CPR.

---

## 14. CPR Magnet Trade

Concept:
- Gap at open.
- CPR positioned near prior close.
- Under suitable conditions, CPR can attract price and help fill the gap.
- Best as an early-session concept.
- CPR becomes destination rather than entry level.

### Vision implication
A virgin/untested CPR or CPR near prior close must be allowed to function as:
- **target/magnet**
as well as:
- support/resistance.

A level should not have a single fixed role.

---

# PART D — CAMARILLA

## 15. Book Camarilla Layers

Book standard:
H1, H2, H3, H4
L1, L2, L3, L4

Expanded:
H5 / L5 as breakout objectives.

### Important Vision note
**The book does not supply Vision's H6/L6 framework.**
H6/L6 are a Vision Trading OS extension and must be clearly labeled as such.
Do not attribute H6/L6 rules to Ochoa.

Vision standard remains:
H3 H4 H5 H6
L3 L4 L5 L6

But:
- H3–H5/L3–L5 can be source-grounded in this book.
- H6/L6 require separate Vision policy/evidence.

---

## 16. Camarilla Meaning

### H3 / L3
Responsive reversal/action zones.

Traditional:
- H3 → look for bearish reversal.
- L3 → look for bullish reversal.

### H4 / L4
Last major resistance/support and initiative breakout zones.

- H4 break/acceptance → bullish breakout.
- L4 break/acceptance → bearish breakout.

But the book also observes H4/L4 can reverse, so **touch is not enough**.

### H5 / L5
Expanded breakout targets.

---

## 17. H3 Reversal

Traditional book framework:

Context:
- Price advances to H3.
- Momentum/behavior begins to weaken.

Trigger:
- Rejection/candlestick evidence at H3.
- Additional confirmation may come from next bar staying below H3 and closing weaker.

Traditional stop:
- at/above H4.

Traditional target:
- L3.

### Vision interpretation
Do **not** implement `touch H3 → short`.

Implement:
`H3 action zone`
+ contextual reversal thesis
+ rejection/price-action trigger
+ acceptable entry location
+ remaining room
→ responsive short candidate.

---

## 18. L3 Reversal

Mirror:

Context:
- Price declines to L3.
- Strength/rejection appears.

Trigger:
- reversal candle / bullish confirmation.
- next bar can confirm by holding above L3 and closing stronger.

Traditional stop:
- at/below L4.

Traditional target:
- H3.

### Vision
`L3 action zone`
+ bullish rejection
+ good location
→ responsive long candidate.

---

## 19. H4 Breakout

Book warning:
**Do not buy the first touch of H4.**

H4 is the last line of resistance and often gets tested/wicked repeatedly.

Preferred confirmation:
- meaningful bullish close above H4 / prior highs.
- acceptance above resistance.
- retest/hold can strengthen.

Traditional stop:
- around/below H3.

Target:
- H5.

### Vision rule
H4 requires:
`TEST → ACCEPTANCE/BREAKOUT → CONFIRMATION`
not:
`TOUCH → BUY`.

---

## 20. L4 Breakout

Mirror:

Preferred confirmation:
- meaningful close below L4.
- initiative selling / acceptance below.
- L3 may act as resistance on retest.

Traditional stop:
- around/above L3.

Target:
- L5.

### Vision
`L4 TEST`
→ `BREAK`
→ `ACCEPTANCE / RETEST`
→ eligible bearish breakout if location still favorable.

---

# PART E — ADVANCED CAMARILLA

## 21. Camarilla Width

Measured by H3–L3 width in the book.

### Unusually Narrow
Expected:
- breakout/trend potential.

Best confirmation:
- opening outside prior range
- preferably beyond third/fourth layer
- initiative behavior

### Unusually Wide
Expected:
- range/sideways tendency.
- traditional H3↔L3 target may become unrealistic.
- inner layers can matter in book framework.

### Vision note
Vision currently focuses H3+ and L3+.
Do not automatically add H1/H2/L1/L2 unless Product Owner approves.
The book's hidden-layer logic is useful evidence but outside current frozen default framework.

---

## 22. Two-Day Camarilla Relationships

Use current H3–L3 range versus prior H3–L3 range.

Same seven relationship families:
- Higher Value
- Overlapping Higher Value
- Lower Value
- Overlapping Lower Value
- Unchanged Value
- Outside Value
- Inside Value

### Higher / Overlapping Higher
Bullish bias.
Opening location determines whether H3 or L3 is the preferred pullback action level.

### Lower / Overlapping Lower
Bearish bias.
Opening location determines whether L3 or H3 is the preferred pullback sell zone.

### Inside Value
Breakout potential.
Stronger with narrow H3–L3 width.
Opening beyond prior range / beyond fourth layer is strong acceptance.

### Outside Value
More range-like expectation.

---

## 23. Camarilla Trending Entry Logic

### Bullish trend
If Higher/Overlapping Higher:
- open above H3 → buy pullback to H3 if it holds.
- open below H3 but above L3 → L3 is preferred bullish action zone.
- open below L3/L4 can reject bullish thesis and shift bearish.

### Bearish trend
If Lower/Overlapping Lower:
- open below L3 → sell pullback to L3 if it rejects.
- open above L3 but below H3 → H3 becomes preferred bearish action zone.
- open above H3/H4 can reject bearish thesis and shift bullish.

This is one of the most important book-derived rules for Vision.

---

## 24. Camarilla Inside-Value Breakout

Conditions improving breakout thesis:
- current H3–L3 inside prior H3–L3
- unusually narrow width
- open beyond prior range
- preferably open beyond H4/L4
- early gap cannot fill / new value accepted
- price-action confirmation

Vision should prepare breakout tactics before market open but must let opening price validate direction.

---

# PART F — OPENING LOCATION

## 25. Opening Relationships

Book's broader value framework gives three important opening categories:

1. In prior range + in value
2. In prior range + out of value
3. Out of prior range + out of value

### In Range + In Value
- balance unchanged
- lower directional conviction
- range/reversal tactics more likely

### In Range + Out of Value
- sentiment shifted somewhat
- need break/acceptance outside prior range for stronger trend conviction

### Out of Range + Out of Value
- largest sentiment shift
- strongest initiative/trend potential if new value accepted
- if price falls back into prior range, breakout can fail and reverse

### Vision requirement
Opening location is a **bias validator**, not just a displayed statistic.

---

# PART G — ACTION ZONES, TRIGGERS & ENTRY

## 26. Book-Derived Entry Sequence

The safest generalized extraction from the entire book is:

### Step 1 — Pre-market hypothesis
From:
- trend
- prior-day behavior
- CPR relationship
- CPR width
- Camarilla relationship
- Camarilla width
- major confluence
- untouched/virgin references

### Step 2 — Opening acceptance/rejection
Ask:
- Did the open confirm the hypothesis?
- Did it reject it?
- Is price in range/value or seeking new value?

### Step 3 — Select action zone
Examples:
- CPR pullback in trend
- H3/L3 reversal zone
- H4/L4 breakout zone
- prior range extreme
- confluence zone

### Step 4 — Observe event
- rejection
- sweep
- BOS/CHoCH
- breakout
- failed breakout
- retest
- wick/outside/extreme/doji behavior

### Step 5 — Trigger
A price-action event must make the trade actionable.

### Step 6 — Check location/asymmetry
- Is destination too close?
- Is move already mature?
- Is this a chase?
- Is there sufficient room?
- Is invalidation sensible?

### Step 7 — Confirm
Option Chain and secondary evidence adjust confidence.

### Step 8 — Execute
Only after:
- thesis valid
- location valid
- trigger valid
- room acceptable
- session eligible

---

# PART H — CONFLUENCE

## 27. Multiple Pivot Hot Zones

Book principle:
Two or more uncorrelated price frameworks aligning in the same zone increase significance.

### Double Pivot Zone
Any two meaningful pivots in the same vicinity.

### Golden Pivot Zone
CPR combined with Camarilla or Money Zone level.

Most relevant Vision combinations:
- CPR + H3 → bearish resistance confluence.
- CPR + L3 → bullish support confluence.

### Important rule
Confluence identifies a **high-interest zone**.
It still needs price-action confirmation.

---

## 28. Vision Confluence Hierarchy

For Vision OS, prioritize existing available data:

Tier 1:
- CPR + Camarilla
- Camarilla + prior high/low
- CPR + prior high/low
- pivot + confirmed market structure

Tier 2:
- pivot + VWAP
- pivot + Opening Range
- pivot + liquidity event

Tier 3 supporting:
- momentum/volume indicators

Option Chain remains a distinct primary confirmation source, not a geometric pivot.

---

# PART I — TARGETS, INVALIDATION & REMAINING ROOM

## 29. Target Selection Must Depend on Day Type

Book repeatedly adjusts targets by:
- pivot width
- trend
- day type
- next pivot/destination
- virgin levels / hot zones

### Narrow/trending environment
- allow larger target / farther pivot.
- trend-day behavior may justify holding longer.

### Wide/range environment
- nearer target.
- avoid unrealistic distant objective.

### Vision rule
A target is not static just because a setup name is the same.

---

## 30. Entry Location vs Destination

This directly supports VM-ENTRY-1.

Example:
Bearish thesis valid, but price already near L3/L4/destination after large move:
- direction may remain bearish
- fresh short can be poor
- use destination as target, not entry
- wait for retest when appropriate

This mirrors the book's virgin-level principle: an early test may be a reversal zone; a late test is often better treated as a target.

---

# PART J — NO-TRADE / WAIT RULES

## 31. Book-Supported Reasons to Stand Aside

- Sideways day with poor participation.
- Abnormally wide pivots with insufficient expected room for intended trade.
- Pivot signal without contextual confirmation.
- First touch of H4/L4 without breakout acceptance.
- Countertrend reversal pattern against aggressive initiative trend.
- Opening rejects pre-market directional thesis.
- Signal forms at poor location.
- Level tested late when it is more appropriately a destination than a reversal entry.
- Market does not respond cleanly/predictably to pivot framework.
- Setup lacks sufficient confirmation for trader's chosen mode.

### Vision states
- `OBSERVE`
- `PREPARE_LONG`
- `PREPARE_SHORT`
- `WAIT_FOR_RETEST`
- `AVOID`
- `LONG_ELIGIBLE`
- `SHORT_ELIGIBLE`

---

# PART K — VISION MORNING FLIGHT PLAN

## 32. Required Pre-Market Pivot Intelligence

Vision should eventually build a concise `PivotFlightPlan` containing:

### Session
- current trading date
- prior completed session
- gap/open relationship

### CPR
- TC / Pivot / BC
- width
- width classification
- two-day relationship
- prior close relation
- expected bias
- expected day-type tendency

### Camarilla
- H3/H4/H5/H6
- L3/L4/L5/L6
- H3–L3 width
- width classification
- two-day relationship
- expected action zones

### Prior Day
- high
- low
- close
- range
- day-type estimate if available

### Confluence
- CPR–Camarilla hot zones
- CPR/Camarilla with prior high/low
- other available structural hot zones

### Scenario A
If opening accepts bullish thesis:
- preferred long action zones
- breakout conditions
- targets
- invalidation concepts

### Scenario B
If opening accepts bearish thesis:
- preferred short action zones
- breakout conditions
- targets
- invalidation concepts

### Scenario C
If opening rejects pre-market thesis:
- exact conditions that invalidate original plan
- opposite-direction zones to watch

This is the book's “Flight Plan” concept translated into Vision OS.

---

# PART L — LIVE REASONING HIERARCHY

## 33. Proposed Vision Decision Hierarchy

```text
PRE-MARKET FLIGHT PLAN
        ↓
OPENING ACCEPTANCE / REJECTION
        ↓
CURRENT DAY-TYPE / REGIME HYPOTHESIS
        ↓
DIRECTIONAL THESIS
        ↓
ACTION ZONE
        ↓
PRICE-ACTION EVENT
        ↓
ENTRY TRIGGER
        ↓
ENTRY LOCATION QUALITY
        ↓
REMAINING ROOM / MOVE MATURITY / CHASE RISK
        ↓
OPTION CHAIN CONFIRMATION
        ↓
FINAL CANDIDATE QUALITY
        ↓
ELIGIBLE / WAIT / AVOID
        ↓
ATM/ITM OPTION SELL CONSTRUCTION
        ↓
OPTION RISK
        ↓
PAPER EXECUTION
```

---

# PART M — BOOK RULE → VISION RULE MAPPING

## 34. H3 Responsive Short

Book:
- H3 test
- weakness/rejection
- optional next-bar confirmation
- H4 stop
- L3 target

Vision:
- H3 action zone
- bearish price-action rejection
- contextual compatibility
- good entry location
- remaining room adequate
- Option Chain modifies confidence
- short eligible only if no chase/location block

---

## 35. L3 Responsive Long

Book:
- L3 test
- strength/rejection
- confirmation
- L4 stop
- H3 target

Vision:
mirror H3 logic.

---

## 36. H4 Initiative Long

Book:
- do not buy first touch
- require bullish breakout/close above
- H3 invalidation area
- H5 target

Vision:
- H4 test state
- breakout event
- acceptance
- optional/retest-aware entry
- no chase if H5/destination too close

---

## 37. L4 Initiative Short

Book:
- require close below / acceptance
- L3 invalidation area
- L5 target

Vision:
mirror H4 logic.

---

## 38. CPR Trend Pullback

Book:
- established bullish trend + CPR acts support → buy dip.
- established bearish trend + CPR acts resistance → sell rip.

Vision:
- trend state
- CPR action zone
- rejection/hold trigger
- structure alignment
- location/asymmetry
- eligible.

---

## 39. Narrow CPR / Narrow Camarilla Breakout

Book:
- narrow width predicts higher breakout probability.
- opening beyond prior range increases conviction.
- early acceptance confirms.

Vision:
- pre-market breakout regime
- do not choose direction solely from narrowness
- opening/price action establishes direction
- retest or clean acceptance triggers.

---

## 40. Wide CPR / Wide Camarilla Range

Book:
- range/sideways expectation.
- smaller target expectations.
- reversal tactics may dominate.

Vision:
- lower breakout confidence
- closer destinations
- more responsive than initiative bias
- possible no-trade.

---

# PART N — OPTION CHAIN INTEGRATION

## 41. Book vs Vision Separation

Ochoa's book does not provide our Option Chain framework.

Therefore Option Chain rules are **Vision-specific**, not book-derived.

Vision policy:

### CONFIRMS
- strengthen final quality/confidence.

### NEUTRAL
- no hard veto if Price Action + location are valid.

### UNAVAILABLE
- no automatic veto; quality reduced.

### CONTRADICTS
- reduce confidence and may keep candidate non-actionable if conflict is severe under approved semantics.

Option Chain cannot create a trade from weak Price Action.

---

# PART O — H6/L6 POLICY

## 42. Source Boundary

The reviewed book includes expanded Camarilla H5/L5 but does **not** establish H6/L6 as part of its Camarilla framework.

Vision's preferred H6/L6 levels remain project-specific.

For VPM-1:
- preserve H6/L6 calculation/display.
- treat them as extreme extension/context levels.
- DO NOT claim book-derived entry/target rules for them.
- formal H6/L6 execution semantics require separate validation/approval.

---

# PART P — WHAT VISION CURRENTLY NEEDS AUDITED

## 43. Implementation Comparison Categories

After this blueprint is approved, Codex should perform a **read-only VPM-2 gap audit**.

For every rule/component classify:

- `IMPLEMENTED_CORRECTLY`
- `IMPLEMENTED_PARTIALLY`
- `IMPLEMENTED_BUT_NOT_USED`
- `MISSING`
- `CONFLICTS_WITH_BOOK_BLUEPRINT`
- `VISION_EXTENSION_NOT_IN_BOOK`

Audit at minimum:

1. Market-day classification
2. Responsive vs initiative behavior
3. CPR two-day relationships
4. CPR opening acceptance/rejection
5. CPR width
6. CPR trend pullbacks
7. CPR magnet/virgin behavior
8. Camarilla two-day relationships
9. Camarilla width
10. H3 reversal
11. L3 reversal
12. H4 breakout acceptance
13. L4 breakout acceptance
14. H5/L5 targets
15. H6/L6 Vision extension
16. Opening relationship
17. Wick reversal
18. Extreme reversal
19. Outside reversal
20. Doji reversal
21. Retest handling
22. Confluence/hot zones
23. Target adaptation by day type
24. Entry-location quality
25. Remaining room
26. Move maturity
27. Chase risk
28. Pre-market Flight Plan
29. Scenario invalidation
30. Option Chain confidence semantics
31. Session/execution guard
32. Forensic explainability

---

# PART Q — FROZEN PRINCIPLES FOR FUTURE IMPLEMENTATION

## 44. Do Not Program These Incorrectly

Never implement:

- H3 touched → automatic short.
- L3 touched → automatic long.
- H4 touched → automatic long.
- L4 touched → automatic short.
- Narrow CPR → automatically bullish/bearish.
- Narrow Camarilla → automatically bullish/bearish.
- CPR below price → automatically bullish.
- CPR above price → automatically bearish.
- Option Chain confirms → trade regardless of Price Action.
- Every candidate must trade.
- Direction valid → entry automatically valid.

---

## 45. Correct Vision Intelligence

Vision should be able to say:

> Pre-market structure is bearish due to Lower Value CPR and Lower Value
> Camarilla. The open accepted that bias below value. Price is now rallying
> into H3/CPR resistance. Bearish rejection has appeared. The thesis is valid,
> location is favorable, and sufficient downside room remains. Option Chain is
> neutral, reducing confidence but not vetoing the setup. SHORT_ELIGIBLE.

Or:

> Bearish structure remains valid, but the market has already extended to L3
> after a mature downside move. Remaining room is poor and chase risk is high.
> Do not sell here. WAIT_FOR_RETEST.

Or:

> Pre-market bias was bullish, but the opening print occurred below L4 and
> outside the prior range. The bullish plan is rejected. Initiative sellers are
> seeking lower value. Switch to bearish breakout/continuation scenarios.

This is the target reasoning standard.

---

# PART R — VPM-1 FINAL OUTPUT

## 46. VPM-1 Verdict

**Book completely reviewed:** YES
**Production code changed:** NO
**Methodology extracted:** YES
**CPR framework extracted:** YES
**Camarilla framework extracted:** YES
**Opening/acceptance logic extracted:** YES
**Pivot-width logic extracted:** YES
**Two-day relationships extracted:** YES
**Trend pullback logic extracted:** YES
**Price-action triggers extracted:** YES
**Confluence logic extracted:** YES
**No-trade principles extracted:** YES
**Flight Plan concept extracted:** YES
**H6/L6 identified as Vision extension, not book rule:** YES

## 47. Recommended Next Milestone

`VPM-2 — Vision OS Book-to-Code Gap Audit`

MODE:
READ ONLY.

Purpose:
Compare the currently frozen Vision Trading OS implementation against
`VISION_PIVOT_METHOD_V1` before changing any production logic.

Only after VPM-2 should we decide which missing capabilities genuinely
belong in production and in what order.
